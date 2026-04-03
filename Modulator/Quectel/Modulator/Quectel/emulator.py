import socket
import threading
import time
import json

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
    "cereg_n": 0,          # režim URC
    "cereg_stat": 0,       # poslední stav registrace
    "tac": "9488",         # Tracking Area Code
    "ci": "94EC9",      # Cell ID
    "act": 9,               # 9 = NB-IoT
    "cfun":1               # 1 registrován rádio
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


def evaluate_at_command(cmd):
    cmd = cmd.strip().upper()

    if cmd == "AT":
        return "OK"

    if cmd == "ATE":
        return "OK"

    if cmd == "AT+QCSQ":
        return f'+QCSQ: "NBIOT",{convert_rsrp_to_rssi(global_state["rsrp"])},{global_state["rsrp"]},119,-8\nOK'

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
            return f'+CEREG: 0,{stat}\nOK'
        if n == 1:
            return f'+CEREG: 1,{stat}\nOK'
        if n == 2:
            return f'+CEREG: 2,{stat},{global_state["tac"]},{global_state["ci"]},{global_state["act"]}\nOK'
        if n == 4:
            return f'+CEREG: 4,{stat},{global_state["tac"]},{global_state["ci"]},{global_state["act"],",,,,"}\nOK'
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

                with mutex:
                    conn.sendall((response + "\n").encode())

            except:
                break

        conn.close()
        print("[AT] Client disconnected")

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
