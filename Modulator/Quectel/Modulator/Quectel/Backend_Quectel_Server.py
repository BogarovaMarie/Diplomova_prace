import json
import socket
import threading
import time

REMOTE_IP = "127.0.0.1"  # localhost
SETTINGS_PORT = 65000  # Náhodně zvolený port z dynamického rozsahu (49152-65535)
AT_PORT = 50000  # Náhodně zvolený port z dynamického rozsahu (49152-65535)


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

    # Vytvoří socket serveru
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)  # Vytvoří TCP/IP socket (AF_INET = IPv4, SOCK_STREAM = TCP)
    sock.bind( (REMOTE_IP, SETTINGS_PORT))  # U serveru NUTNÉ vázat socket na IP a port, aby bylo jasné, kde se bude naslouchat
    # U klienta to nutné není, tam stačí jen connect() protože OS si sám vybere volný odchozí port.
    sock.settimeout(60)  # Nastaví timeout na 5 sekund pro operace s tímto socketem pokud je nežádoucí blokování programu.
    sock.listen(1)  # Nastaví socket do režimu naslouchání, s maximální délkou fronty 1 čekající připojení.
    # Konkurentně totiž můžeš mít více klientů (ne v této aplikaci, ale obecně), ale tady je to
    # pro jednoduchost omezeno na 1.
    print("Server is listening on {}:{}".format(REMOTE_IP, SETTINGS_PORT))

    # vytvoření vláken pro další činnosti
    th1 = threading.Thread(target=doSomethingElse, daemon=True)
    th1.start()  # spustí vlákno
    th2 = threading.Thread(target=doSomethingElse1, daemon=True)
    th2.start()  # spustí vlákno

    try:  # Čeká na připojení klienta. Zde nutný try-except kvůli timeoutu.
        conn, addr = sock.accept()  # Blokuje program až do příchodu připojení klienta (nebo timeout)
        print("Connection from:", addr)  # Vytiskne IP a port připojeného klienta
        data = conn.recv(1460)                                                                        # Přijme až 1460 bajtů dat od klienta p5ijme jednu zpr8vu a pak se zavře
        json_data = json.loads(data.decode())  # Převede přijatá data z JSON formátu na slovník
        print(json_data)
        rsrp = json_data.get("rsrp", "---")
        band = json_data.get("band", "---")
        print(f" RSRP: {json_data['rsrp']} band: {json_data['band']}")
         # udelej neco s daty
        if b'Hello' in data:
            doSomething()
            print(data)
    except socket.timeout:
        print("Socket timed out, no data received.")
        # Vytiskne zprávu o timeoutu, toto bude otravné, reálně asi použij "pass".



rsrp = None
band = None

def uloz_nastaveni(rsrp_value, band_value):
    global rsrp, band
    rsrp = rsrp_value
    band = band_value

# Python
# Definice slovníku s příkazy a odpověďmi
prikazy_odpovedi = {
    ("AT","ATE"): "OK",
    "AT+QCSQ": "<CR>AT+QCSQ<CR>+QCSQ: \"NBIoT\",-99,-110,119,-8 \n 0",
    "AT+GMI": "AT+GMI<CR> \n Quectel \n \n OK",
    "AT+CGMI": "AT+CGMI<CR> \n Quectel \n \n OK",
    "AT+GMM": "AT+GMM<CR> \n BG77 \n \n OK",
    "AT+CGMM": "AT+CGMM<CR> \n BG77 \n \n OK",
    "AT+CEREG?": " \n CEREG: 0,5 \n \n OK",
    "AT+GSN": "AT + GSN < CR > \n 866349045095357 \n \n OK",
    "ATI": "ATI<CR> \n Quectel \n BG77 \n Revision: BG77LAR02A04 \n \n OK"
}

# Funkce pro získání odpovědi

@staticmethod
def get_odpoved(prikaz):
    """
        Vrátí odpověď podle zadaného příkazu.
        Pokud příkaz neexistuje, vrátí výchozí zprávu.
        """
    # Úprava vstupu (velká písmena, odstranění mezer)
    cmd = prikaz.strip().upper()
    for varianty, odpoved in prikazy_odpovedi.items():
        if cmd in varianty:
            return odpoved
    return "Neznám tento příkaz."
 #   return prikazy_odpovedi.get(cmd, "Neznám tento příkaz.")


