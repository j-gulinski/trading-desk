import os
import time
import json
import logging
import threading
import queue
import urllib.request
import urllib.error
from wsgiref.simple_server import make_server, WSGIServer
from socketserver import ThreadingMixIn
import bottle
from bottle import route, run, response, ServerAdapter

from shared import INSTRUMENTS, get_iso_timestamp

STREAM_URL = os.getenv("STREAM_URL")

app = bottle.Bottle()

lock = threading.Lock()
market_data_connection = 'DISCONNECTED'
ticks_received = 0
client_event_queues = []
last_event_timestamp = None

market_state = {
    data["instrument_id"]: data.copy() for key, data in INSTRUMENTS.items()
}

def market_data_stream_consumer():
    global market_data_connection, ticks_received, last_event_timestamp, market_state
    while True:
        logging.info(f"Connecting to Market Data Stream at {STREAM_URL}...")
        try:
            request = urllib.request.Request(STREAM_URL)
            with urllib.request.urlopen(request) as stream:
                with lock:
                    market_data_connection = 'CONNECTED'
                for line in stream:
                    decoded_line = line.decode('utf-8').strip()
                    if not decoded_line:
                        continue
                    logging.debug(f"Received tick from stream: {decoded_line}")
                    if decoded_line.startswith('data: '):
                        raw_json = decoded_line[6:]
                        tick = json.loads(raw_json)
                        
                        with lock:
                            ticks_received += 1
                            last_event_timestamp = tick['timestamp']
                            update_pricing(tick)
        except urllib.error.URLError as e:
            logging.error(f"Stream connection failed: {e}. Retrying in 5 seconds...")
        except Exception as e:
            logging.error(f"Unexpected error: {e}. Retrying in 5 seconds...")
        finally:
            with lock:
                market_data_connection = 'DISCONNECTED'
        with lock:
            market_data_connection = 'RECONNECTING'
        time.sleep(5)
        
def update_pricing(tick):
    instrument_id = tick['instrument_id']
    asset_type = tick['asset_type']
    if instrument_id in market_state:
        if asset_type == 'EQUITY':
            market_state[instrument_id]['bid'] = tick['bid']
            market_state[instrument_id]['ask'] = tick['ask']
            market_state[instrument_id]['last'] = tick['last']

            market_state[instrument_id]['fair_value'] = round((tick['bid'] + tick['ask']) / 2, 4)
        elif asset_type == 'BOND':
            market_state[instrument_id]['yield'] = tick['yield']

            market_state[instrument_id]['fair_value'] = round(calculate_bond_fair_value(
                market_state[instrument_id]['face_value'],
                market_state[instrument_id]['coupon_rate'],
                market_state[instrument_id]['maturity_years'],
                market_state[instrument_id]['payments_per_year'],
                tick['yield']
            ), 4)
        elif asset_type == 'FX_FORWARD':
            market_state[instrument_id]['spot'] = tick['spot']
            market_state[instrument_id]['domestic_rate'] = tick['domestic_rate']
            market_state[instrument_id]['foreign_rate'] = tick['foreign_rate']

            market_state[instrument_id]['fair_value'] = round((
                tick['spot'] 
                * (1 + tick['domestic_rate'] * market_state[instrument_id]['tenor_years']) 
                / (1 + tick['foreign_rate'] * market_state[instrument_id]['tenor_years'])
            ), 4)
        for q in client_event_queues:
            q.put({
                "instrument_id": market_state[instrument_id]['instrument_id'],
                "fair_value": market_state[instrument_id]['fair_value'],
                "currency": market_state[instrument_id]['currency'],
                "timestamp": tick['timestamp']
            })

def calculate_bond_fair_value(face_value, coupon_rate, maturity_years, payments_per_year, yield_rate):
    annual_coupon = face_value * coupon_rate
    total_periods = int(maturity_years * payments_per_year)
    price = 0
    for t in range(1, total_periods + 1):
        cashflow = annual_coupon / payments_per_year
        
        if t == total_periods:
            cashflow += face_value
        
        present_value = cashflow / (1 + yield_rate / payments_per_year) ** t
        price += present_value
    return price

@app.route('/valuations')
def get_valuations():
    response.content_type = 'application/json'
    with lock:
        return market_state.copy()

@app.route('/valuation/<instrument_id>')
def get_valuation(instrument_id):
    response.content_type = 'application/json'
    with lock:
        if instrument_id in market_state:
            return market_state[instrument_id].copy()
        return {"error": "Instrument not found"}
    
@app.route('/stream')
def stream():
    response.content_type = 'text/event-stream'

    client_q = queue.Queue()
    logging.info("New client connected to /stream endpoint")

    with lock:
        client_event_queues.append(client_q)
    
    def generate_events():
        try:
            while True:
                tick = client_q.get()
                yield f"event: valuation_update\ndata: {json.dumps(tick)}\n\n" 
        except Exception:
            pass
        finally:
            with lock:
                if client_q in client_event_queues:
                    client_event_queues.remove(client_q)
                    logging.info("Client disconnected from /stream endpoint")
            
    return generate_events()

@app.route('/health')
def health():
    global market_data_connection, ticks_received, last_event_timestamp

    with lock:
        return {
            "service": "pricing-service",
            "status": "UP",
            "market_data_connection": market_data_connection,
            "received_events": ticks_received,
            "last_market_event_time": last_event_timestamp,
        }
    
class ThreadedServer(ServerAdapter):
    def run(self, handler):
        class ThreadingWSGIServer(ThreadingMixIn, WSGIServer):
            daemon_threads = True
        server = make_server(self.host, self.port, handler, server_class=ThreadingWSGIServer)
        server.serve_forever()

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    logging.info("Starting Pricing Service...")
    threading.Thread(target=market_data_stream_consumer, daemon=True).start()
    app.run(host='0.0.0.0', port=8002, server=ThreadedServer)