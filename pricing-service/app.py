import time
import socket

server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
server.bind(('0.0.0.0', 8002))
server.listen()

while True:
    client, address = server.accept()
    client.send("Welcome to the Pricing Service!\n".encode())
    time.sleep(2)
    client.send('Disconnecting...'.encode())
    client.close()