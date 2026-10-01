import asyncio
import json
import sys
import time
from urllib.parse import urlsplit

PROBES = 5
UPDATE = b"event: valuation"


class Window:
    def __init__(self, warmup, seconds):
        self.start = time.monotonic() + warmup
        self.end = self.start + seconds
        self.seconds = seconds
        self.updates = 0
        self.delays = []

    def open(self):
        return time.monotonic() < self.end

    def measuring(self):
        return time.monotonic() >= self.start


async def connect(url):
    reader, writer = await asyncio.open_connection(url.hostname, url.port)
    writer.write(f"GET {url.path} HTTP/1.1\r\nHost: {url.hostname}\r\n\r\n".encode())
    await writer.drain()
    status = await reader.readline()
    if b" 200 " not in status:
        raise ConnectionError(status.decode().strip())
    return reader, writer


async def hold(reader, window):
    while window.open():
        chunk = await reader.read(65536)
        if not chunk:
            raise ConnectionError("stream closed")
        if window.measuring():
            window.updates += chunk.count(UPDATE)


async def probe(reader, window):
    while window.open():
        line = await reader.readline()
        if not line:
            raise ConnectionError("stream closed")
        if line.startswith(b"data: ") and window.measuring():
            window.updates += 1
            window.delays.append(time.time() - json.loads(line[6:])["published_at"])


def percentile(values, share):
    ordered = sorted(values)
    return round(1000 * ordered[min(len(ordered) - 1, int(share * len(ordered)))], 2)


async def main(url, count, warmup, seconds):
    streams = await asyncio.gather(*(connect(url) for _ in range(count)), return_exceptions=True)
    connected = [stream for stream in streams if not isinstance(stream, Exception)]
    window = Window(warmup, seconds)
    readers = [
        probe(reader, window) if index < PROBES else hold(reader, window)
        for index, (reader, _) in enumerate(connected)
    ]
    outcomes = await asyncio.gather(*readers, return_exceptions=True)
    for _, writer in connected:
        writer.close()
    delays = window.delays
    return {
        "subscribers": count,
        "connected": len(connected),
        "dropped": sum(isinstance(outcome, Exception) for outcome in outcomes),
        "seconds": seconds,
        "updates_received": window.updates,
        "delivery_ms": {
            name: percentile(delays, share)
            for name, share in (("p50", 0.5), ("p95", 0.95), ("p99", 0.99), ("max", 1.0))
        } if delays else None,
    }


if __name__ == "__main__":
    target, count, warmup, seconds = sys.argv[1], *map(int, sys.argv[2:5])
    print(json.dumps(asyncio.run(main(urlsplit(target), count, warmup, seconds))))
