import socket

# -----------------------------
# SERVER na portu 5000 (non-blocking)
# -----------------------------
server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
server_socket.bind(("127.0.0.1", 5000))
server_socket.listen(5)
server_socket.setblocking(False)  # non-blocking režim

print("Server běží na 127.0.0.1:5000 (non-blocking)")