# Market Data Streaming System

## 1. System Description
The Market Data Streaming system is a lightweight, real-time microservices architecture built in Python. It simulates a financial ecosystem where market data (ticks for Equities, Bonds, and FX Forwards) is generated in real-time, consumed by a pricing engine to calculate live fair values, and monitored by a centralized health-checking service.

## 2. Architecture Description
The system is composed of three primary microservices:
*   **Market Data Service (Port 8001)**: Acts as the source of truth for raw market data. It continuously generates randomized ticks for configured financial instruments and broadcasts them to connected clients.
*   **Pricing Service (Port 8002)**: Subscribes to the Market Data Service. It applies financial models (e.g., discounted cash flow for bonds, interest rate parity for FX forwards) to calculate the real-time fair value of the instruments and re-broadcasts the updated valuations.
*   **Monitoring Service (Port 8003)**: A watchdog service that continuously polls the health status of both the Market Data and Pricing services, keeping track of their uptime, response times, and connection statuses.

## 3. How to Run
Prerequisites: Docker and Docker Compose installed.

The application must be run using `docker-compose` because the `shared` module is required by all services and must be properly mounted or moved into each service container.

To start the entire system, run the following command in the root of the project:

```bash
docker-compose up --build
```

## 4. Endpoints Description
### Market Data Service (8001)
*   `GET /stream`: Server-Sent Events (SSE) endpoint broadcasting raw market ticks.
*   `GET /snapshot`: Returns a JSON snapshot of the current state of all market instruments.
*   `GET /health`: Returns the health status and the number of generated events.

### Pricing Service (8002)
*   `GET /stream`: Server-Sent Events (SSE) endpoint broadcasting calculated valuation updates.
*   `GET /valuations`: Returns a JSON object containing the latest calculated fair values and states for all tracked instruments.
*   `GET /valuation/<instrument_id>`: Returns the latest state and valuation for a specific instrument (e.g., `EQ_ACME`).
*   `GET /health`: Returns the health status, including the connection state to the upstream market data stream.

### Monitoring Service (8003)
*   `GET /status`: Returns a JSON payload with the latest aggregated health metrics and response times for the Market Data and Pricing services.
*   `GET /health`: Basic health check for the monitoring service itself.

## 5. Inter-service Communication
*   **Streaming**: The Pricing Service connects to the Market Data Service via a persistent one-way HTTP connection using Server-Sent Events (SSE). It reads the stream line-by-line using standard `urllib.request`.
*   **Polling**: The Monitoring Service communicates with the other services via periodic asynchronous HTTP GET requests to their `/health` endpoints to evaluate their availability and latency.

## 6. Streaming Mechanism
The streaming mechanism is implemented using Server-Sent Events (SSE). 
*   In Bottle, this is achieved by returning a Python generator function (e.g., `yield f"data: {json.dumps(tick)}\n\n"`) from the route handler.
*   When a client connects to a `/stream` endpoint, a new `queue.Queue()` is created and appended to a globally shared list of client queues. Background threads push new events into these queues, and the generator yields them to the open HTTP socket, keeping the connection alive indefinitely.

## 7. Concurrency Mechanism
The project uses standard OS threads to achieve concurrency:
*   **Web Server Concurrency**: The built-in WSGI server is wrapped with Python's `ThreadingMixIn`, allowing it to handle each incoming HTTP request (and long-lived SSE connection) in a separate thread.
*   **Background Tasks**: Dedicated daemon threads are spawned on startup (`threading.Thread(..., daemon=True).start()`) to handle continuous background loops (e.g., generating market data, consuming SSE streams, polling health checks).
*   **Thread Safety**: A `threading.Lock()` is heavily utilized across all services to protect shared state (like instrument dictionaries, metric counters, and client queue lists) from race conditions and concurrent mutation errors.

## 8. How to Test the System
You can test the system using `curl` or any web browser:
1.  **Check System Health**: Run `curl http://localhost:8003/status` to ensure all services are recognized as "UP".
2.  **Verify Live Valuations**: Run `curl http://localhost:8002/valuations` multiple times to see the fair values updating as new market data arrives.
3.  **Test Streams**: Run `curl http://localhost:8001/stream` or `curl http://localhost:8002/stream` in your terminal. You should see a continuous flow of JSON objects printing to your screen in real time.

## 9. Implementation Problems Encountered
- overcoming initial lack of knowledge of python threading - (GIL, threads, multiprocessing)
- no parallel threads in single process - deamon processes for continous tasks