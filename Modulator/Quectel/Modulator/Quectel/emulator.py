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
    "band": "B20",
    "cereg_n": 0,               # režim URC
    "cereg_stat": 0,            # poslední stav registrace
    "tac": "9488",              # Tracking Area Code
    "ci": "94EC9",              # Cell ID
    "act": 9,                   # 9 = NB-IoT
    "iotopmode": 1,             # aktuální RAT (1 = NB-IoT)
    "iotopmode_pending": None,  # hodnota, která se aplikuje po restartu
    "cfun":1                    # 1 registrován rádio
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
                conn.sendall((response + "\n").encode())
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
        msg = f'+CEREG: {stat}\n'
    else:
        msg = f'+CEREG: {stat},{global_state["tac"]},{global_state["ci"]},{global_state["act"]}\n'

    for conn in at_clients:
        try:
            conn.sendall(msg.encode())
        except:
            pass

## toto by se mělo přepočítávat pro všechny parametry pro QCSQ vyzkoušet a zapsat
# -----------------------------
# AT PŘÍKAZY – LOGIKA
# -----------------------------
def convert_rsrp_to_rssi(rsrp):
    # hrubá simulace
    if rsrp > -80: return 20
    if rsrp > -90: return 15
    if rsrp > -100: return 10
    if rsrp > -110: return 5
    return 0

def calculate_rsrq(rsrp_dbm, rssi_dbm, N=1):
    rsrp_mw = 10 ** (rsrp_dbm / 10)
    rssi_mw = 10 ** (rssi_dbm / 10)
    rsrq_linear = (N * rsrp_mw) / rssi_mw
    rsrq_db = 10 * math.log10(rsrq_linear)
    return round(rsrq_db, 1)

# nevím jak to definovat, můžu to zkust aproximovat takto?
def estimate_sinr(rssi):
    if rssi <= -100:
        return 119
    if rssi <= -98:
        return 134
    if rssi <= -93:
        return 193



# Propisování Band do AT příkazů nápověda v GUI.py poznámka dole
# chci tam switch case pro 4 typy příkazů, nebude v tom zmatek?

def evaluate_at_command(cmd):
    cmd = cmd.strip().upper()

    if cmd in ("AT", "ATE"):
        return {"delay": 0.8, "response": "OK"}

    if cmd=="AT+GMI":
        return {"now": "AT+GMI<CR> \n Quectel \n \n OK"}

    if cmd == "AT+CGMI":
        return {"now": "AT+CGMI<CR> \n Quectel \n \n OK"}

    if cmd == "AT+GMM":
        return {"now": "AT+GMM<CR> \n BG77 \n \n OK"}

    if cmd == "AT+CGMM":
        return {"now": "AT+CGMM<CR> \n BG77 \n \n OK"}

    if cmd == "AT+GSN":
        return {"now": "AT + GSN < CR > \n 866349045095357 \n \n OK"}

    if cmd == "ATI":
        return {"now": "ATI<CR> \n Quectel \n BG77 \n Revision: BG77LAR02A04 \n \n OK"}

    if cmd == "AT+QCSQ":
        rssi = convert_rsrp_to_rssi(global_state["rsrp"])
        rsrp = global_state["rsrp"]
        sinr = estimate_sinr(rssi)
        rsrq = calculate_rsrq(rsrp, rssi)

        resp = f'+QCSQ: "NBIOT",{rssi},{rsrp},{sinr},{rsrq}\nOK'
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
                return {"now": f'+QCFG: "iotopmode",{mode},1\nOK'}
            else:
                return {"now": f'+QCFG: "iotopmode",{pending},0\nOK'}

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

            return {"delay": 0.5, "response": "OK"}

        except:
            return {"now": "ERROR"}

    if cmd.startswith("AT+CFUN="):
        try:
            mode = int(cmd.split("=")[1])
            if mode in (0, 1):
                global_state["cfun"] = mode
                return "OK"
            return "ERROR"
        except:
            return "ERROR"

    if cmd == "AT+CEREG=?":
        return f'+CEREG: (0-2,4)\nOK'

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
            resp = f'+CEREG: 0,{stat}\nOK'
        elif n == 1:
            resp = f'+CEREG: 1,{stat}\nOK'
        elif n == 2:
            resp = f'+CEREG: 2,{stat},{global_state["tac"]},{global_state["ci"]},{global_state["act"]}\nOK'
        elif n == 4:
            resp = f'+CEREG: 4,{stat},{global_state["tac"]},{global_state["ci"]},{global_state["act"]},,,,\nOK'

        return {"delay": 1.5, "response": resp}

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
                        conn.sendall((result["now"] + "\n").encode())
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
