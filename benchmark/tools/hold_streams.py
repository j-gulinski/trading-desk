import socket
import sys
import time
from urllib.parse import urlsplit

url, count, out_path = urlsplit(sys.argv[1]), int(sys.argv[2]), sys.argv[3]
streams = []
for _ in range(count):
    sock = socket.create_connection((url.hostname, url.port))
    sock.sendall(f"GET {url.path} HTTP/1.1\r\nHost: {url.hostname}\r\n\r\n".encode())
    sock.setblocking(False)
    streams.append(sock)

time.sleep(2)
answered = 0
for sock in streams:
    try:
        answered += sock.recv(65536).startswith((b"HTTP/1.1 200", b"HTTP/1.0 200"))
    except BlockingIOError:
        pass
with open(out_path, "w") as out:
    out.write(f"requested={count} answered={answered}\n")
time.sleep(3600)
