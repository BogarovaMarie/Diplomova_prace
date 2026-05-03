# Python 3 script to send a TCP message
import socket

# Server IP and port
host = "127.0.0.1"
port = 2020

# Message to send
message = "Hello, TCP Server!"

# Create a socket object
with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
    try:
        s.connect((host, port))  # Connect to the server
        s.sendall(message.encode('utf-8'))  # Send message
        response = s.recv(1024)  # Receive response if any
        print("Received from server:", response.decode('utf-8'))
    except ConnectionRefusedError:
        print("Connection failed. Make sure a server is listening on this port.")