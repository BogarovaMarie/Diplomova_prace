import socket
import threading
import time
import json
import math

# -----------------------------
# KONSTANTY
# -----------------------------
AT_PORT = 50000
SETTINGS_PORT = 65000

# -----------------------------
# GLOBÁLNÍ STAV
# -----------------------------
mutex = threading.Lock()

at_clients = []
timers = []
global_state = {
    "rsrp": -100,
    "rssi": -90,
    "sinr": 10,
    "band": "B20",
    "cereg_n": 0,               # režim URC
    "cereg_stat": 0,            # poslední stav registrace
    "tac": "9488",              # Tracking Area Code
    "ci": "94EC9",              # Cell ID
    "act": 9,                   # 9 = NB-IoT
    "iotopmode": 1,             # aktuální RAT (1 = NB-IoT)
    "iotopmode_pending": None,  # hodnota, která se aplikuje po restartu
    "cfun":1,                   # 1 registrován rádio
    "sockets": {}               # slovník otevřených socketů: connect_id -> socket_info
}

# -----------------------------
# TIMER OBJEKT
# -----------------------------
class Timer:
    def __init__(self, delay, callback=None):
        self.timestamp = time.time()
        self.delay = delay
        self.expired = False
        self.callback = callback

    def check(self):
        if not self.expired and time.time() - self.timestamp >= self.delay:
            self.expired = True
            if self.callback:
                self.callback()

# -----------------------------
# FUNKCE PRO PLÁNOVANÉ ODPOVĚDI ("ZPOŽDĚNÍ")
# -----------------------------
def schedule_response(conn, response, delay):
        def callback():
            try:
                conn.sendall((response + "\r\n").encode())
            except:
                pass

        timers.append(Timer(delay, callback))

    # -----------------------------
    # CEREG
    # -----------------------------
def send_cereg_urc(stat):
    n = global_state["cereg_n"]

    if n == 0:
        return  # URC vypnuto

    if n == 1:
        msg = f'+CEREG: {stat}\r\n'
    else:
        msg = f'+CEREG: {stat},{global_state["tac"]},{global_state["ci"]},{global_state["act"]}\r\n'

    for conn in at_clients:
        try:
            conn.sendall(msg.encode())
        except:
            pass

## toto by se mělo přepočítávat pro všechny parametry pro QCSQ vyzkoušet a zapsat
# -----------------------------
# AT PŘÍKAZY – LOGIKA
# -----------------------------
#def convert_rsrp_to_rssi(rsrp):
#    # hrubá simulace
#    if rsrp > -80: return 20
#    if rsrp > -90: return 15
#    if rsrp > -100: return 10
#    if rsrp > -110: return 5
#    return 0

def calculate_rsrq(rsrp_dbm, rssi_dbm, N=1):
    rsrp_mw = 10 ** (rsrp_dbm / 10)
    rssi_mw = 10 ** (rssi_dbm / 10)
    rsrq_linear = (N * rsrp_mw) / rssi_mw
    rsrq_db = 10 * math.log10(rsrq_linear)
    return int(round(rsrq_db))

# nevím jak to definovat, můžu to zkust aproximovat takto?
#def estimate_sinr(rssi):
#    if rssi <= -100:
#        return 119
#   if rssi <= -98:
#        return 134
#    if rssi <= -93:
#        return 193
#    return 200  # default, aby nikdy nevrátil None

# Propisování Band do AT příkazů nápověda v GUI.py poznámka dole
# chci tam switch case pro 4 typy příkazů, nebude v tom zmatek?

def manage_socket(connect_id, ip_address, remote_port):
    """Správa socketu v samostatném vlákně"""
    try:
        # Vytvoření TCP socketu
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(10)  # timeout pro připojení
        
        print(f"[SOCKET {connect_id}] Connecting to {ip_address}:{remote_port}")
        
        # Pokus o připojení
        sock.connect((ip_address, remote_port))
        
        # Aktualizace stavu na connected
        with mutex:
            if connect_id in global_state["sockets"]:
                global_state["sockets"][connect_id]["status"] = "connected"
                global_state["sockets"][connect_id]["socket"] = sock
        
        print(f"[SOCKET {connect_id}] Connected successfully")
        
        # Hlavní smyčka pro příjem dat
        sock.settimeout(1)  # timeout pro recv
        while True:
            try:
                data = sock.recv(1024)
                if not data:
                    # Socket byl uzavřen ze strany serveru
                    break
                
                print(f"[SOCKET {connect_id}] Received: {data.decode(errors='ignore')}")
                
                # Zde by mohla být logika pro zpracování příchozích dat
                # Např. odeslání URC +QIRD nebo podobně
                
            except socket.timeout:
                # Timeout - pokračujeme ve smyčce
                continue
            except:
                break
        
    except Exception as e:
        print(f"[SOCKET {connect_id}] Connection failed: {e}")
        # Aktualizace stavu na failed
        with mutex:
            if connect_id in global_state["sockets"]:
                global_state["sockets"][connect_id]["status"] = "failed"
    
    finally:
        # Uzavření socketu
        try:
            sock.close()
        except:
            pass
        
        # Aktualizace stavu na closed
        with mutex:
            if connect_id in global_state["sockets"]:
                global_state["sockets"][connect_id]["status"] = "closed"
        
        print(f"[SOCKET {connect_id}] Socket closed")

def evaluate_at_command(cmd):
    cmd = cmd.strip().upper()

    if cmd in ("AT", "ATE"):
        return {"delay": 0.206, "response": "OK"}

    if cmd=="AT+GMI":
        return {"now": "AT+GMI<CR>\nQuectel\r\n\r\nOK"}

    if cmd == "AT+CGMI":
        return {"now": "AT+CGMI<CR>\nQuectel\r\n\r\nOK"}

    if cmd == "AT+GMM":
        return {"now": "AT+GMM<CR>\nBG77\r\n\r\nOK"}

    if cmd == "AT+CGMM":
        return {"now": "AT+CGMM\r\nBG77\r\n\r\nOK"}

    if cmd == "AT+GSN":
        return {"now": "AT+GSN<CR>\r\n866349045095357\r\n\r\nOK"}

    if cmd == "ATI":
        return {"now": "ATI<CR>\nQuectel\r\nBG77\r\nRevision: BG77LAR02A04\r\n\r\nOK"}

    if cmd == 'AT+QCFG="band"':
        return {"delay": 0.077, "response": '+QCFG: "band",0x0,0x80084,0x80084\r\n\r\nOK'}

    if cmd == "AT+QCSQ":
        rssi = global_state["rssi"]
        rsrp = global_state["rsrp"]
        sinr = global_state["sinr"]
        rsrq = calculate_rsrq(rsrp, rssi)

        resp = f'+QCSQ: "NBIOT",{rssi},{rsrp},{sinr},{rsrq}\r\nOK'
        return {"delay": 0.4, "response": resp}

    # ---------------------------------------------------------
    # AT+QCFG="iotopmode"
    # ---------------------------------------------------------
    if cmd.startswith('AT+QCFG="IOTOPMODE"'):
        parts = cmd.split(",")

        # dotaz bez parametrů
        if len(parts) == 1:
            mode = global_state["iotopmode"]
            pending = global_state["iotopmode_pending"]
            if pending is None:
                return {"now": f'+QCFG: "iotopmode",{mode},1\r\nOK'}
            else:
                return {"now": f'+QCFG: "iotopmode",{pending},0\r\nOK'}

        # nastavení dvou parametrů
        try:
            mode = int(parts[1])
            apply_now = int(parts[2])

            if mode not in (0, 1) or apply_now not in (0, 1):
                return {"now": "ERROR"}

            if apply_now == 1:
                # aplikovat ihned
                global_state["iotopmode"] = mode
                global_state["act"] = 9 if mode == 1 else 8
                global_state["iotopmode_pending"] = None
            else:
                # uložit, ale neaplikovat
                global_state["iotopmode_pending"] = mode

            return {"delay": 0.955, "response": "OK"}

        except:
            return {"now": "ERROR"}

    # ---------------------------------------------------------
    # AT+CFUN=?  (dotaz na podporované režimy)
    # ---------------------------------------------------------
    if cmd == "AT+CFUN=?":
        resp = '+CFUN: (0,1,4),(0,1)\r\nOK'
        return {"delay": 0.079, "response": resp}

    # ---------------------------------------------------------
    # AT+CFUN=<mode>  (nastavení režimu)
    # ---------------------------------------------------------
    if cmd.startswith("AT+CFUN="):
        try:
            mode = int(cmd.split("=")[1])
            if mode in (0, 1):
                global_state["cfun"] = mode
                return {"delay": 0.140, "response": f"AT+CFUN={mode}\r\nOK"}
            return {"now": "ERROR"}
        except:
            return {"now": "ERROR"}

    # ---------------------------------------------------------
    # AT+CFUN?  (dotaz na aktuální režim)
    # ---------------------------------------------------------
    if cmd == "AT+CFUN?":
        mode = global_state["cfun"]
        resp = f'+CFUN: {mode}\r\n OK'
        return {"delay": 0.032, "response": resp}

    if cmd == "AT+CEREG=?":
        resp= f'+CEREG: (0-2,4)\r\n OK'
        return {"delay": 0.079, "response": resp}

    #Error má taky různé stupně upovídanosti, zapracovat taky do kódu?
    # ---------------------------------------------------------
    # AT+CEREG=<n>  (nastavení URC režimu)
    # ---------------------------------------------------------
    if cmd.startswith("AT+CEREG="):
        try:
            n = int(cmd.split("=")[1])
            if n in (0, 1, 2, 4):
                global_state["cereg_n"] = n
                return "OK"
            else:
                return "ERROR"
        except:
            return "ERROR"

    # ---------------------------------------------------------
    # AT+CEREG?  (dotaz na stav registrace)
    # ---------------------------------------------------------
    if cmd == "AT+CEREG?":
        n = global_state["cereg_n"]

        # CFUN=0 → modem není registrován
        if global_state["cfun"] == 0:
            stat = 0
        else:
            rsrp = global_state["rsrp"]
            if rsrp > -90:
                stat = 1
            elif rsrp > -110:
                stat = 5
            else:
                stat = 2

        global_state["cereg_stat"] = stat

        if n == 0:
            resp = f'+CEREG: 0,{stat}\r\nOK'
        elif n == 1:
            resp = f'+CEREG: 1,{stat}\r\nOK'
        elif n == 2:
            resp = f'+CEREG: 2,{stat},{global_state["tac"]},{global_state["ci"]},{global_state["act"]}\r\nOK'
        elif n == 4:
            resp = f'+CEREG: 4,{stat},{global_state["tac"]},{global_state["ci"]},{global_state["act"]},,,,\r\nOK'

        return {"delay": 0.032, "response": resp}

    # ---------------------------------------------------------
    # AT+QIOPEN  (otevření socketu)
    # ---------------------------------------------------------
    if cmd.startswith("AT+QIOPEN="):
        try:
            # Parsování parametrů: AT+QIOPEN=<contextID>,<connectID>,<service_type>,<IP_address>,<remote_port>
            params = cmd.split("=")[1].split(",")
            if len(params) >= 5:
                context_id = int(params[0])
                connect_id = int(params[1])
                service_type = params[2].strip('"')
                ip_address = params[3].strip('"')
                remote_port = int(params[4])
                
                # Kontrola, zda connect_id není již použit
                if connect_id in global_state["sockets"]:
                    return {"now": "ERROR"}
                
                # Spuštění socket vlákna pro tento connect_id
                socket_thread = threading.Thread(target=manage_socket, args=(connect_id, ip_address, remote_port), daemon=True)
                socket_thread.start()
                
                # Uložení informace o otevřeném socketu do globálního stavu
                global_state["sockets"][connect_id] = {
                    "context_id": context_id,
                    "service_type": service_type,
                    "ip_address": ip_address,
                    "remote_port": remote_port,
                    "status": "connecting"
                }
                
                print(f"[QIOPEN] Opening socket: context={context_id}, connect={connect_id}, type={service_type}, ip={ip_address}:{remote_port}")
                
                # Odpověď s URC +QIOPEN a pak OK
                urc_response = f'+QIOPEN: {connect_id},0\r\n'
                return {"delay": 1.0, "response": urc_response + "OK"}
            else:
                return {"now": "ERROR"}
        except:
            return {"now": "ERROR"}

    # ---------------------------------------------------------
    # AT+QISEND  (odeslání dat přes socket)
    # ---------------------------------------------------------
    if cmd.startswith("AT+QISEND="):
        try:
            # Parsování parametrů: AT+QISEND=<connectID>,<send_length>
            params = cmd.split("=")[1].split(",")
            if len(params) >= 2:
                connect_id = int(params[0])
                send_length = int(params[1])
                
                # Kontrola, zda socket existuje a je připojen
                if connect_id not in global_state["sockets"] or global_state["sockets"][connect_id]["status"] != "connected":
                    return {"now": "ERROR"}
                
                # V emulátoru jednoduše potvrdíme přijetí příkazu
                # V reálném modemu by zde čekal na data k odeslání
                return {"delay": 0.1, "response": ">"}
            else:
                return {"now": "ERROR"}
        except:
            return {"now": "ERROR"}

    # ---------------------------------------------------------
    # AT+QICLOSE  (zavření socketu)
    # ---------------------------------------------------------
    if cmd.startswith("AT+QICLOSE="):
        try:
            # Parsování parametrů: AT+QICLOSE=<connectID>
            connect_id = int(cmd.split("=")[1])
            
            # Kontrola, zda socket existuje
            if connect_id not in global_state["sockets"]:
                return {"now": "ERROR"}
            
            # Uzavření socketu
            try:
                if "socket" in global_state["sockets"][connect_id]:
                    global_state["sockets"][connect_id]["socket"].close()
            except:
                pass
            
            # Aktualizace stavu
            global_state["sockets"][connect_id]["status"] = "closed"
            
            print(f"[QICLOSE] Closed socket {connect_id}")
            
            return {"delay": 0.2, "response": "OK"}
        except:
            return {"now": "ERROR"}

## Odesílá přes socket s jiným portem než settings (AT_PORT, AT_SETTINGS_PORT)
#musí se to předávat JSONem? tady se to předává bez toho...
# -----------------------------
# VLÁKNO 1 – AT SOCKET
# -----------------------------
def at_thread():
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind(("127.0.0.1", AT_PORT))
    server.listen(1)
    print(f"[AT] Listening on port {AT_PORT}")

    while True:
        conn, addr = server.accept()
        print("[AT] Client connected:", addr)

        while True:
            try:
                data = conn.recv(1024)
                if not data:
                    break

                cmd = data.decode().strip()
                print("[AT] Received:", cmd)

                response = evaluate_at_command(cmd)

                result = evaluate_at_command(cmd)

                with mutex:
                    if "now" in result:
                        conn.sendall((result["now"] + "\r\n").encode())
                    elif "delay" in result:
                        schedule_response(conn, result["response"], result["delay"])

            except:
                break

        conn.close()
        print("[AT] Client disconnected")

#Nějaké další parametry?
# -----------------------------
# VLÁKNO 2 – SETTINGS SOCKET
# -----------------------------
def settings_thread():
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind(("127.0.0.1", SETTINGS_PORT))
    server.listen(1)
    print(f"[SETTINGS] Listening on port {SETTINGS_PORT}")

    while True:
        conn, addr = server.accept()
        print("[SETTINGS] Client connected:", addr)

        data = conn.recv(1024)
        if data:
            try:
                json_data = json.loads(data.decode())
                print("[SETTINGS] Received:", json_data)

                with mutex:
                    global_state["rsrp"] = json_data.get("rsrp", global_state["rsrp"])
                    global_state["rssi"] = json_data.get("rssi", global_state["rssi"])
                    global_state["sinr"] = json_data.get("sinr", global_state["sinr"])
                    global_state["band"] = json_data.get("band", global_state["band"])

                print("[SETTINGS] Updated state:", global_state)

            except json.JSONDecodeError:
                print("[SETTINGS] Invalid JSON")

        conn.close()
#asi nadbytečné!
      #  old_stat = global_state["cereg_stat"]

        # po aktualizaci RSRP:
      #  new_stat = vypocitej_stat(global_state["rsrp"])

       # if new_stat != old_stat:
      #      global_state["cereg_stat"] = new_stat
       #     send_cereg_urc(new_stat)

## timer zatím neaplikován, potřebuji, aby to vypisovalo zpoždění podle printscreenů, resp. realizovalo v AT příkazech
# -----------------------------
# VLÁKNO 0 – MAIN (TIMERS)
# -----------------------------
def timer_thread():
    while True:
        with mutex:
            for t in timers:
                t.check()
        time.sleep(0.1)

# -----------------------------
# START
# -----------------------------
if __name__ == "__main__":
    print("BG77 Emulator starting...")

    threading.Thread(target=timer_thread, daemon=True).start()
    threading.Thread(target=at_thread, daemon=True).start()
    threading.Thread(target=settings_thread, daemon=True).start()

    while True:
        time.sleep(1)
