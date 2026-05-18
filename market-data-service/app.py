import time
import threading
import queue
import json
import random
from bottle import run, response, ServerAdapter
from wsgiref.simple_server import make_server, WSGIServer
from socketserver import ThreadingMixIn
from shared import INSTRUMENTS, get_iso_timestamp
import bottle

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

app = bottle.Bottle()

def market_data_generator():
    global ticks_generated, last_event_timestamp

    while True:
        now = get_iso_timestamp()

        with lock:
            current_equity_mid = (snapshot["ACME"]["bid"] + snapshot["ACME"]["ask"]) / 2

            new_equity_mid = max(1.0, current_equity_mid + random.uniform(-0.2, 0.2))

            tick_acme = {
                "event_id": ticks_generated,
                "timestamp": now,
                "asset_type": "EQUITY",
                "symbol": "ACME",
                "bid": round(new_equity_mid - 0.05, 2),
                "ask": round(new_equity_mid + 0.05, 2),
                "last": round(new_equity_mid + random.uniform(-0.02, 0.02), 2)
            }

            ticks_generated += 1
            last_event_timestamp = now

            ticks = [tick_acme]

            snapshot["ACME"].update({"bid": tick_acme["bid"], "ask": tick_acme["ask"], "last": tick_acme["last"]})


            for q in client_event_queues:
                for t in ticks:
                    q.put(t)
        
        time.sleep(0.5)
        
@app.route('/stream')
def stream():
    response.content_type = 'text/event-stream'
    response.headers['Cache-Control'] = 'no-cache'
    response.headers['Connection'] = 'keep-alive'
    response.headers['Transfer-Encoding'] = 'chunked'

    client_q = queue.Queue()

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
            
    return generate_events()

@app.route('/snapshot')
def get_snapshot():
    response.content_type = 'application/json'
    with lock:
        return snapshot
    
@app.route('/health')
def health():
    global ticks_generated, last_event_timestamp
    return {
        "service": "Market Data Service",
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
    threading.Thread(target=market_data_generator, daemon=True).start()
    app.run(host='0.0.0.0', port=8001, server=ThreadedServer)