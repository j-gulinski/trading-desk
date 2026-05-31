import logging
import threading
from app.api import app
from app.market_data_client import market_data_stream_consumer
from app.valuation_publisher import ThreadedServer

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    logging.info("Starting Pricing Service...")
    threading.Thread(target=market_data_stream_consumer, daemon=True).start()
    app.run(host="0.0.0.0", port=8002, server=ThreadedServer)
