import socket
import threading
import time
import json
import math
import subprocess
import re
import platform

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
    "ber":0,
    "band": "BAND 20",
    "cereg_n": 0,               # režim URC
    "cereg_stat": 0,            # poslední stav registrace
    "tac": "9488",              # Tracking Area Code
    "ci": "94EC9",              # Cell ID
    "act": 9,                   # 9 = NB-IoT
    "iotopmode": 1,             # aktuální RAT (1 = NB-IoT)
    "iotopmode_pending": None,  # hodnota, která se aplikuje po restartu
    "cfun":1,                   # 1 registrován rádio
    "mcc": "230",               # Mobile Country Code (Česká republika)
    "mnc": "02",                # Mobile Network Code (O2)
    "exec_mode": "NBIoT",       # NBIoT/eMTC
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

def get_ping_response(ip_address, timeout_ms):
    """
    Provede ping a vrátí reply_time v ms a TTL
    Funguje na Windows i Linuxu/macOS
    """
    system = platform.system()  # 'Windows', 'Linux', 'Darwin' (macOS)

    try:
        if system == 'Windows':
            # Windows příkaz: ping -n 1 -w timeout_ms
            cmd = ["ping", ip_address, "-n", "1", "-w", str(timeout_ms)]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout_ms / 1000 + 2)
            output = result.stdout

            # Parsování Windows výstupu: "time=50ms TTL=64"
            time_match = re.search(r"time[<=]*([0-9]+)ms", output)
            ttl_match = re.search(r"TTL[<=]*([0-9]+)", output)

            if time_match:
                reply_time = int(time_match.group(1))
                ttl = int(ttl_match.group(1)) if ttl_match else 64
                return reply_time, ttl
            return None, None

        else:  # Linux, macOS
            # Linux/macOS příkaz: ping -c 1 -W timeout_ms ip
            timeout_sec = max(1, timeout_ms // 1000)
            cmd = ["ping", "-c", "1", "-W", str(timeout_sec), ip_address]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout_sec + 2)
            output = result.stdout

            # Parsování Linux výstupu: "time=50.1 ms" a "ttl=64"
            time_match = re.search(r"time[<=]*([0-9.]+)\s*ms", output)
            ttl_match = re.search(r"ttl[<=]*([0-9]+)", output, re.IGNORECASE)

            if time_match:
                reply_time = int(float(time_match.group(1)))
                ttl = int(ttl_match.group(1)) if ttl_match else 64
                return reply_time, ttl
            return None, None
    except Exception as e:
        print(f"Ping error: {e}")
        return None, None


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
    # ---------------------------------------------------------
    # AT+CSQ - report o kvalitě signálu
    # ---------------------------------------------------------
    if cmd == "AT+CSQ":
        # RSSI převod z dBm na index podle 3GPP TS 27.007
        rssi_dbm = global_state.get("rssi", -90)
        if rssi_dbm <= -113:
            rssi_val = 0
        elif rssi_dbm >= -51:
            rssi_val = 31
        else:
            # 2 až 30: -109 až -53 dBm, krok 2 dBm
            rssi_val = int(round((rssi_dbm + 113) / 2))
            if rssi_val < 0:
                rssi_val = 0
            elif rssi_val > 31:
                rssi_val = 31
        ber_val = global_state.get("ber", 0)# BER v procentech, 0 = <0.2%
        resp = f'+CSQ: {rssi_val},{ber_val}\r\nOK'
        return {"now": resp}

    if cmd in ("AT", "ATE"):
        return {"delay": 0.206, "response": "\r\n\r\nOK"}

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

        resp = f'+QCSQ: "NBIOT",{rssi},{rsrp},{sinr},{rsrq}\r\n\r\nOK'
        return {"delay": 0.4, "response": resp}

    # ---------------------------------------------------------
    # AT+QNWINFO - Network Information
    # ---------------------------------------------------------
    if cmd.startswith("AT+QNWINFO"):
        if cmd.endswith("=?"):
             # Testovací príkaz
            return {"now": '\r\nOK'}
        elif cmd.endswith("?") or cmd == "AT+QNWINFO":
            # Dotazovací a prováděcí - vrátí aktuální stav sítě
            # Mapování exec_mode: 1 = eMTC, 2 = NB-IoT (podle global_state["iotopmode"])
            iotopmode = global_state.get("iotopmode", 1)
            exec_mode_str = "eMTC" if iotopmode == 0 else "NBIoT"
            band_str = global_state.get("band", '"LTE" band 20')
            # MCC-MNC kombinace (230=CZ, 02=O2, 03=T-Mobile, itd.)
            mcc_mnc = global_state.get("mcc", "230") + global_state.get("mnc", "02")

            # Pseudo-náhodné číslo (může být PCI nebo jiný identifikátor)
            import random
            cell_id_num = int(global_state.get("ci", "94EC9"), 16) % 10000

            resp = f'+QNWINFO: "{exec_mode_str}","{mcc_mnc}","{band_str}",{cell_id_num}\r\n\r\nOK'
            return {"now": resp}
        else:
            return {"now": "ERROR"}

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
                return {"now": f'+QCFG: "iotopmode",{mode},1\r\n\r\nOK'}
            else:
                return {"now": f'+QCFG: "iotopmode",{pending},0\r\n\r\nOK'}

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

            return {"delay": 0.955, "response": "\r\n\r\nOK"}

        except:
            return {"now": "ERROR"}

        # ---------------------------------------------------------
        # AT+COPS - výběr operátora
        # ---------------------------------------------------------
    if cmd.startswith("AT+COPS"):
        if cmd.endswith("=?"):
            # Testovací příkaz: AT+COPS=?
            # Vrací seznam dostupných režimů a operátorů (zde zjednodušeně)
            return {
                    "now": '+COPS: (2,"O2-CZ","O2-CZ","23002",9),(1,"T-Mobile CZ","TMO CZ","23001",9),(0,"Vodafone CZ","VDF CZ","23003",9)\r\n\r\nOK'}
        elif cmd.endswith("?"):
            # Dotazovací příkaz: AT+COPS?
            # Vrací aktuální nastavení (zde zjednodušeně)
            # Příklad: +COPS: 0,0,"O2-CZ",9
            return {"now": '+COPS: 1,0,"Vodafone",act\r\nOK'}
        elif "=" in cmd:
            # Nastavovací příkaz: AT+COPS=<mode>[,<format>[,<oper>[,<act>]]]
            # Zpracování parametrů (zde pouze validace a simulace)
            try:
                params = cmd.split("=")[1].split(",")
                mode = int(params[0])
                # Další parametry lze zpracovat dle potřeby
                # Např. format, oper, act
                # Zde pouze simulace úspěšného nastavení
                return {"now": "OK"}
            except:
                return {"now": "ERROR"}
        else:
            # Prováděcí příkaz: AT+COPS
            # Vrací základní informace (zde zjednodušeně)
            return {"now": '+COPS: 1,0,"Vodafone",act\r\nOK'}

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

#netuším, jestli modem opravdu takto počítá celevel, ale můžu to zkusit aproximovat podle RSRP, aby se to nějak měnilo a nebylo to pořád stejné, když se změní RSRP v nastavení
    if cmd == 'AT+QCFG="celevel"':
        # Odvození celevel podle RSRP
        rsrp = global_state.get("rsrp", -100)
        if rsrp > -110:
            celevel = 0  # nejlepší pokrytí
        elif rsrp > -120:
            celevel = 1
        else:
            celevel = 2
        return {"now": f'+QCFG: "celevel",{celevel}\r\nOK'}

    if cmd.startswith("AT+QPING"):
        if cmd.endswith("=?"):
            return {"now": '+QPING: (<contextID>),(<IP>),(<timeout>),(<bytes>)\r\nOK'}
        elif "=" in cmd:
            try:
                parts = cmd.split("=")[1].split(",")
                if len(parts) >= 2:
                    ip_address = parts[1].strip().strip('"')
                    timeout = int(parts[2]) if len(parts) > 2 else 4000  # ms
                    bytes_size = int(parts[3]) if len(parts) > 3 else 32

                    reply_time, ttl = get_ping_response(ip_address, timeout)
                    if reply_time is not None:
                        resp = f'+QPING: "{ip_address}",{reply_time},{ttl},{bytes_size}\r\n\r\nOK'
                        return {"now": resp}
                    else:
                        return {"now": "ERROR"}
                else:
                    return {"now": "ERROR"}
            except Exception as e:
                print("Ping error:", e)
                return {"now": "ERROR"}
        else:
            return {"now": "ERROR"}

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

        while True:
            try:
                data = conn.recv(1024)
                if not data:
                    break

                json_data = json.loads(data.decode())
                print("[SETTINGS] Received (raw):", json_data)

                # Normalizujeme klíče na malá písmena pro flexibilitu
                normalized_data = {k.lower(): v for k, v in json_data.items()}
                print("[SETTINGS] Received (normalized):", normalized_data)

                with mutex:
                    # Aktualizujeme jen klíče, které jsou přítomny
                    if "rsrp" in normalized_data:
                        global_state["rsrp"] = normalized_data["rsrp"]
                    if "rssi" in normalized_data:
                        global_state["rssi"] = normalized_data["rssi"]
                    if "sinr" in normalized_data:
                        global_state["sinr"] = normalized_data["sinr"]
                    if "band" in normalized_data:
                        global_state["band"] = normalized_data["band"]

                print("[SETTINGS] Updated state:", global_state)

                # Pošli potvrzení
                conn.sendall(b"OK\r\n")

            except json.JSONDecodeError as e:
                print("[SETTINGS] Invalid JSON:", e)
                conn.sendall(b"ERROR\r\n")
                break
            except Exception as e:
                print("[SETTINGS] Exception:", e)
                break

        conn.close()
        print("[SETTINGS] Client disconnected")


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
