import logging
import threading
from app.api import app
from app.generator import market_data_generator
from app.publisher import ThreadedServer

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    logging.info("Starting Market Data Service...")
    threading.Thread(target=market_data_generator, daemon=True).start()
    app.run(host="0.0.0.0", port=8001, server=ThreadedServer)
