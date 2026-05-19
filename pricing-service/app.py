import os
import time
import json
import logging
import threading
import urllib.request
import urllib.error
from wsgiref.simple_server import make_server, WSGIServer
from socketserver import ThreadingMixIn
import bottle
from bottle import route, run, response, ServerAdapter

from shared import INSTRUMENTS, get_iso_timestamp

STREAM_URL = os.getenv("STREAM_URL")

app = bottle.Bottle()

market_data_connection = 'DISCONNECTED'
ticks_received = 0
last_event_timestamp = None

market_state = {
    data["instrument_id"]: data for key, data in INSTRUMENTS.items()
}

def market_data_stream_consumer():
    global market_data_connection, ticks_received, last_event_timestamp, market_state
    while True:
        logging.info(f"Connecting to Market Data Stream at {STREAM_URL}...")
        try:
            request = urllib.request.Request(STREAM_URL)
            with urllib.request.urlopen(request) as stream:
                market_data_connection = 'CONNECTED'
                for line in stream:
                    decoded_line = line.decode('utf-8').strip()
                    if not decoded_line:
                        continue
                    logging.debug(f"Received tick from stream: {decoded_line}")
                    if decoded_line.startswith('data: '):
                        raw_json = decoded_line[6:]
                        tick = json.loads(raw_json)
                        
                        ticks_received += 1
                        last_event_timestamp = tick['timestamp']
                        
                        update_pricing(tick)
        except urllib.error.URLError as e:
            logging.error(f"Stream connection failed: {e}. Retrying in 5 seconds...")
        except Exception as e:
            logging.error(f"Unexpected error: {e}. Retrying in 5 seconds...")
        finally:
            market_data_connection = 'DISCONNECTED'
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
            market_state[instrument_id]['fair_value'] = (tick['bid'] + tick['ask']) / 2

@app.route('/valuations')
def get_valuations():
    response.content_type = 'application/json'
    return json.dumps(market_state)

@app.route('/valuation/<instrument_id>')
def get_valuation(instrument_id):
    response.content_type = 'application/json'
    return json.dumps(market_state.get(instrument_id, {"error": "Instrument not found"}))

@app.route('/health')
def health():
    global market_data_connection, ticks_received, last_event_timestamp
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