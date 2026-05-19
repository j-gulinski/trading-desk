import time
import threading
import queue
import json
import random
import logging
import bottle
from bottle import run, response, ServerAdapter
from wsgiref.simple_server import make_server, WSGIServer
from socketserver import ThreadingMixIn

from shared import INSTRUMENTS, get_iso_timestamp

app = bottle.Bottle()

lock = threading.Lock()
ticks_generated = 0
last_event_timestamp = None
client_event_queues = []

snapshot = {
    inst["market_symbol"]: {
        "asset_type": inst["type"],
        "market_symbol": inst["market_symbol"]
    }
    for inst in INSTRUMENTS.values()
}

snapshot["ACME"].update({"bid": 99.95, "ask": 100.05, "last": 100.01})


def generate_equity_tick(timestamp):
    global ticks_generated, last_event_timestamp, snapshot
    
    current_equity_mid = (snapshot["ACME"]["bid"] + snapshot["ACME"]["ask"]) / 2

    new_equity_mid = max(1.0, current_equity_mid + random.uniform(-0.2, 0.2))
    
    equity_tick = {
        "event_id": ticks_generated,
        "timestamp": timestamp,
        "instrument_id": "EQ_ACME",
        "asset_type": "EQUITY",
        "symbol": "ACME",
        "bid": round(new_equity_mid - 0.05, 4),
        "ask": round(new_equity_mid + 0.05, 4),
        "last": round(new_equity_mid + random.uniform(-0.02, 0.02), 4)
    }
    snapshot["ACME"].update({"bid": equity_tick["bid"], "ask": equity_tick["ask"], "last": equity_tick["last"]})
    
    return equity_tick

def market_data_generator():
    global ticks_generated, last_event_timestamp, snapshot

    while True:
        now = get_iso_timestamp()
        tick = None

        with lock:
            # tick_type = random.choice(['EQUITY', 'BOND', 'FX_FORWARD'])
            tick_type = random.choice(['EQUITY'])
            if tick_type == 'EQUITY':
                tick = generate_equity_tick(now)
            
            logging.debug(f"Generated tick for {tick['symbol']}: {tick}")

            ticks_generated += 1
            last_event_timestamp = now
            logging.debug(f"Total ticks generated: {ticks_generated}")

            for q in client_event_queues:
                q.put(tick)
        
        time.sleep(0.1)
        
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
                yield f"data: {json.dumps(tick)}\n\n" 
        except Exception:
            pass
        finally:
            with lock:
                if client_q in client_event_queues:
                    client_event_queues.remove(client_q)
                    logging.info("Client disconnected from /stream endpoint")
            
    return generate_events()

@app.route('/snapshot')
def get_snapshot():
    response.content_type = 'application/json'
    with lock:
        return json.dumps(snapshot)
    
@app.route('/health')
def health():
    global ticks_generated, last_event_timestamp

    with lock:
        return {
            "service": "market-data-service",
            "status": "UP",
            "generated_events": ticks_generated,
            "last_event_timestamp": last_event_timestamp
        }


class ThreadedServer(ServerAdapter):
    def run(self, handler):
        class ThreadingWSGIServer(ThreadingMixIn, WSGIServer):
            daemon_threads = True
        server = make_server(self.host, self.port, handler, server_class=ThreadingWSGIServer)
        server.serve_forever()

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    logging.info("Starting Market Data Service...")
    threading.Thread(target=market_data_generator, daemon=True).start()
    app.run(host='0.0.0.0', port=8001, server=ThreadedServer)