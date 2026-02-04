import socket
import threading
import time
import json

REMOTE_IP = "127.0.0.1"  # localhost
REMOTE_PORT = 65000  # Náhodně zvolený port z dynamického rozsahu (49152-65535)
REMOTE_PORT_2 = 65001  # Náhodně zvolený port z dynamického rozsahu (49152-65535)


# Pro každý socket musí být použit jiný port!

# funkce, ktera dela neco s daty
def doSomething():
    print("Doing something!")


# funkce, ktera dela neco s daty něco jiného
def doSomethingElse():
    while True:
        print("Doing something else!")
        time.sleep(1)


# funkce, ktera dela neco s daty ještě něco jiného
def doSomethingElse1():
    while True:
        print("Doing something else11111!")
        time.sleep(1)


# Hlavní funkce main
if __name__ == "__main__":

    # vytvoření vláken pro další činnosti
    th1 = threading.Thread(target=doSomethingElse)
    th1.start()  # spustí vlákno
    th2 = threading.Thread(target=doSomethingElse1)
    th2.start()  # spustí vlákno

    # Vytvoří socket serveru
    sock = socket.socket(socket.AF_INET,
                         socket.SOCK_STREAM)  # Vytvoří TCP/IP socket (AF_INET = IPv4, SOCK_STREAM = TCP)
    sock.bind(
        (REMOTE_IP, REMOTE_PORT))  # U serveru NUTNÉ vázat socket na IP a port, aby bylo jasné, kde se bude naslouchat
    # U klienta to nutné není, tam stačí jen connect() protože OS si sám vybere volný odchozí port.
    sock.settimeout(
        5)  # Nastaví timeout na 5 sekund pro operace s tímto socketem pokud je nežádoucí blokování programu.
    sock.listen(1)  # Nastaví socket do režimu naslouchání, s maximální délkou fronty 1 čekající připojení.
    # Konkurentně totiž můžeš mít více klientů (ne v této aplikaci, ale obecně), ale tady je to
    # pro jednoduchost omezeno na 1.
    print("Server is listening on {}:{}".format(REMOTE_IP, REMOTE_PORT))
    try:  # Čeká na připojení klienta. Zde nutný try-except kvůli timeoutu.
        conn, addr = sock.accept()  # Blokuje program až do příchodu připojení klienta (nebo timeout)
        print("Connection from:", addr)  # Vytiskne IP a port připojeného klienta

        data = conn.recv(1460)  # Přijme až 1460 bajtů dat od klienta

        json_data = json.loads(data.decode())  # Převede přijatá data z JSON formátu na slovník
        print(json_data)
        print(f" RSRP: {json_data['rsrp']}")
        # udelej neco s daty
        if b'Hello' in data:
            doSomething()
        # print(data)
    except socket.timeout:  # Ošetření výjimky při timeoutu
        print(
            "Socket timed out, no data received.")  # Vytiskne zprávu o timeoutu, toto bude otravné, reálně asi použij "pass".
