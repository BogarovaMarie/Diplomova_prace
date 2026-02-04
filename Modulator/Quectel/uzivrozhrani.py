import socket
import json

# Nastavení IP a portu serveru
REMOTE_IP = "127.0.0.1"  # localhost
REMOTE_PORT = 65000  # Náhodně zvolený port z dynamického rozsahu (49152-65535)

if __name__ == "__main__":
    # Vytvoří socket klienta
    sock = socket.socket(socket.AF_INET,
                         socket.SOCK_STREAM)  # Vytvoří TCP/IP socket (AF_INET = IPv4, SOCK_STREAM = TCP)
    sock.connect((REMOTE_IP,
                  REMOTE_PORT))  # Připojí se k serveru na zadanou IP a port (proběhne TCP handshake SYN, SYN-ACK, ACK)

    # Tady uzivatel neco zada
    json_data = {"rsrp": -100}  # Vytvoří slovník, který bude později převeden na JSON
    js = json.dumps(json_data)  # Převede slovník na JSON formát
    sock.sendall(js.encode())  # Odešle JSON na server

    sock.close()  # Uzavře socket klienta (Pošle FIN paket na ukončení spojení)


