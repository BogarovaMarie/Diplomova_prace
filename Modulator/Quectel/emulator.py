import socket
import threading
import time
import json
import math
import subprocess
import re
import platform
import queue

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
    "sockets": {},             # slovník otevřených socketů: connect_id -> socket_info
    "pdp_contexts": {
    i: {"state": 0, "type": 1, "ip_address": ""} for i in range(1, 16)
}
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

# ---------------------------------------------------------
# FRONTA PRO SOCKET OPERACE (QIOPEN, QISEND, QICLOSE, QIRD)
# ---------------------------------------------------------
socket_queue = queue.Queue()

def socket_worker():
    """Dedikované vlákno pro zpracování socket operací (paralelní, nezávislé)"""
    while True:
        cmd = socket_queue.get()
        try:
            result = evaluate_at_command(cmd)
            print(f"[SOCKET_WORKER] Processed: {cmd}")
            print(f"[SOCKET_WORKER] Result: {result}")
        except Exception as e:
            print(f"[SOCKET_WORKER] Error: {e}")
        socket_queue.task_done()

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
            # Správné pořadí na Windows: ping -n 1 -w timeout ip
            cmd = ["ping", "-n", "1", "-w", str(timeout_ms), ip_address]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=max(10, timeout_ms / 1000 + 5))
            output = result.stdout

            # Parsování Windows výstupu: "time=50ms TTL=64"
            time_match = re.search(r"time\s*=\s*(\d+)\s*ms", output, re.IGNORECASE)
            ttl_match = re.search(r"TTL\s*=\s*(\d+)", output, re.IGNORECASE)

            if time_match:
                reply_time = int(time_match.group(1))
                ttl = int(ttl_match.group(1)) if ttl_match else 64
                return reply_time, ttl
            return None, None

        else:  # Linux, macOS
            # Linux/macOS příkaz: ping -c 1 -W timeout_ms ip
            timeout_sec = max(10, timeout_ms / 1000 + 5)
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


def manage_socket(connect_id, ip_address, remote_port, service_type="TCP"):
    """
    Spuštěno v separátním vlákně.
    Simuluje otevření a správu socketu.
    """
    try:
        print(f"[SOCKET {connect_id}] Connecting to {service_type} {ip_address}:{remote_port}")

        # SIMULACE: hned nastavit status na "connected" bez skutečného připojení
        # (V reálném modemu by se tady skutečně připojilo)
        with mutex:
            if connect_id in global_state["sockets"]:
                global_state["sockets"][connect_id]["status"] = "connected"

        print(f"[SOCKET {connect_id}] Connected successfully (simulated)")

        # Připojení k socketu:
        try:
            if service_type.upper() == "UDP":
                sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                sock.settimeout(2)  # krátký timeout
            else:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(2)  # krátký timeout - aby se nezacyklilo
                sock.connect((ip_address, remote_port))

            print(f"[SOCKET {connect_id}] Real connection established")

            with mutex:
                if connect_id in global_state["sockets"]:
                    global_state["sockets"][connect_id]["socket"] = sock

            # Čtení dat v cyklu
            sock.settimeout(5)
            while True:
                try:
                    data = sock.recv(1024)
                    if not data:
                        break

                    print(f"[SOCKET {connect_id}] Received {len(data)} bytes")

                    with mutex:
                        if connect_id in global_state["sockets"]:
                            global_state["sockets"][connect_id]["rx_buffer"] += data

                except socket.timeout:
                    continue
                except:
                    break

        except socket.timeout:
            print(f"[SOCKET {connect_id}] Connection timeout (simulace pokračuje)")
        except Exception as e:
            print(f"[SOCKET {connect_id}] Real connection failed (simulace pokračuje): {e}")

        finally:
            try:
                sock.close()
            except:
                pass

    except Exception as e:
        print(f"[SOCKET {connect_id}] Error: {e}")
        with mutex:
            if connect_id in global_state["sockets"]:
                global_state["sockets"][connect_id]["status"] = "failed"

    finally:
        print(f"[SOCKET {connect_id}] Socket handler ended")


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

    # AT+QCFG="<param>"
    if cmd.upper().startswith('AT+QCFG="') and cmd.endswith('"'):
        # Extrahuj parametr z uvozovek
        param = cmd[9:-1].lower()  # Vezmi mezi AT+QCFG=" a "

        if param == "band":
                return {"delay": 0.077, "response": '+QCFG: "band",0x0,0x80084,0x80084\r\n\r\nOK'}

        elif param == "celevel":
            rsrp = global_state.get("rsrp", -100)
            if rsrp > -110:
                celevel = 0
            elif rsrp > -120:
                celevel = 1
            else:
                celevel = 2
            return {"now": f'+QCFG: "celevel",{celevel}\r\nOK'}

        # ---------------------------------------------------------
        # AT+COPS - výběr operátora
        # ---------------------------------------------------------
    if cmd.startswith("AT+COPS"):
        if cmd.endswith("=?"):
            # Testovací příkaz: AT+COPS=?
            # Vrací seznam dostupných režimů a operátorů (zde zjednodušeně)
            return {
                    "now": f'+COPS: (2,"O2-CZ","O2-CZ","23002",9),(1,"T-Mobile CZ","TMO CZ","23001",9),(0,"Vodafone CZ","VDF CZ","23003",9)\r\n\r\nOK'}
        elif cmd.endswith("?"):
            # Dotazovací příkaz: AT+COPS?
            # Vrací aktuální nastavení (zde zjednodušeně)
            # Příklad: +COPS: 0,0,"O2-CZ",9
            return {"now": f'+COPS: 1,0,"Vodafone",act\r\nOK'}
  #      elif "=" in cmd:
  #          # Nastavovací příkaz: AT+COPS=<mode>[,<format>[,<oper>[,<act>]]]
  #          # Zpracování parametrů (zde pouze validace a simulace)
  #          try:
  #              params = cmd.split("=")[1].split(",")
  #              mode = int(params[0])
                # Další parametry lze zpracovat dle potřeby
                # Např. format, oper, act
                # Zde pouze simulace úspěšného nastavení
   #             return {"now": "OK"}
   #         except:
   #             return {"now": "ERROR"}
        else:
            # Prováděcí příkaz: AT+COPS
            # Vrací základní informace (zde zjednodušeně)
            return {"now": f'+COPS: 1,0,"Vodafone",act\r\nOK'}

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
                return {"now": "OK"}
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

    if cmd.startswith("AT+QPING"):
        if cmd.endswith("=?"):
            return {"now": '+(<contextID>),(<ip_address>),(<timeout>),(<pingnum>)\r\nOK'}
        elif "=" in cmd:
            try:
                parts = cmd.split("=")[1].split(",")
                if len(parts) >= 2:
                    ip_address = parts[1].strip().strip('"')
                    timeout = int(parts[2]) if len(parts) > 2 else 4000  # ms
                    ping_num = int(parts[3]) if len(parts) > 3 else 1

                    # Vrátit speciální instrukci pro naplánování
                    return {
                        "ping_sequence": {
                            "ip_address": ip_address,
                            "timeout": timeout,
                            "ping_num": ping_num
                        }
                    }
                else:
                    return {"now": "ERROR"}
            except Exception as e:
                print("Ping error:", e)
                return {"now": "ERROR"}
        else:
            return {"now": "ERROR"}

    # AT+QIACT=?
    if cmd == "AT+QIACT=?":
        return {"now": "+QIACT: (1-16)\r\nOK"}

    # AT+QIACT?
    if cmd == "AT+QIACT?":
        resp = ""
        for i in range(1, 16):
            ctx = global_state["pdp_contexts"][i]
            if ctx["state"] == 1:
                resp += f'+QIACT: {i},1,{ctx["type"]},"{ctx["ip_address"]}"\r\n'
            else:
                resp += f'+QIACT: {i},0,{ctx["type"]}\r\n'
        resp += "OK"
        return {"now": resp}

    # AT+QIACT=<contextID>
    if cmd.startswith("AT+QIACT="):
        try:
            context_id = int(cmd.split("=")[1])
            # Zkontroluj limit aktivních kontextů (např. max 2 pro NB2)
            active = sum(1 for c in global_state["pdp_contexts"].values() if c["state"] == 1)
            if active >= 2:
                return {"now": "ERROR"}
            # Aktivuj kontext
            ctx = global_state["pdp_contexts"][context_id]
            ctx["state"] = 1
            ctx["ip_address"] = f"10.0.0.{context_id}"
            return {"now": "OK"}
        except Exception as e:
            return {"now": "ERROR"}

    # AT+QIDEACT=<contextID>
    if cmd.startswith("AT+QIDEACT="):
        try:
            context_id = int(cmd.split("=")[1])
            ctx = global_state["pdp_contexts"][context_id]
            ctx["state"] = 0
            ctx["ip_address"] = ""
            # Zavři všechny sockety s tímto context_id
            to_close = [cid for cid, sock in global_state["sockets"].items() if sock.get("context_id") == context_id]
            for cid in to_close:
                try:
                    if "socket" in global_state["sockets"][cid]:
                        global_state["sockets"][cid]["socket"].close()
                except:
                    pass
                del global_state["sockets"][cid]
            return {"now": "OK"}
        except Exception as e:
            return {"now": "ERROR"}

    # ---------------------------------------------------------
    # AT+QISTATE  (Query Socket Service Status)
    # ---------------------------------------------------------

    # AT+QISTATE=?
    if cmd == "AT+QISTATE=?":
        return {"now": "OK"}

    # AT+QISTATE? nebo AT+QISTATE (Query all sockets)
    if cmd in ("AT+QISTATE?", "AT+QISTATE"):
        resp = ""
        for connect_id, socket_info in global_state["sockets"].items():
            # Mapování stavu socketu
            # 0 = Initial, 1 = Opening, 2 = Connected, 3 = Listening, 4 = Closing
            status_map = {
                "connecting": 1,  # Opening
                "connected": 2,  # Connected
                "listening": 3,  # Listening
                "closing": 4,  # Closing
                "failed": 0  # Initial (error state)
            }
            socket_state = status_map.get(socket_info.get("status", "connecting"), 0)

            service_type = socket_info.get("service_type", "TCP")
            ip_address = socket_info.get("ip_address", "127.0.0.1")
            remote_port = socket_info.get("remote_port", 0)
            local_port = socket_info.get("local_port", 0)
            context_id = socket_info.get("context_id", 1)
            access_mode = socket_info.get("access_mode", 0)

            # serverID je platné pouze pro TCP INCOMING - zatím je None (nezpracováváme)
            server_id = 0

            # AT_port: "usbmodem" nebo "uart1"
            at_port = "usbmodem"

            resp += f'+QISTATE: {connect_id},"{service_type}","{ip_address}",{remote_port},{local_port},{socket_state},{context_id},{server_id},{access_mode},"{at_port}"\r\n'

        resp += "OK"
        return {"now": resp}

    # AT+QISTATE=0,<contextID> (Query all sockets in a specific context)
    if cmd.startswith("AT+QISTATE=0,"):
        try:
            context_id = int(cmd.split("=")[1].split(",")[1])
            resp = ""

            for connect_id, socket_info in global_state["sockets"].items():
                # Filtruj jen sockety s daným context_id
                if socket_info.get("context_id") != context_id:
                    continue

                status_map = {
                    "connecting": 1,
                    "connected": 2,
                    "listening": 3,
                    "closing": 4,
                    "failed": 0
                }
                socket_state = status_map.get(socket_info.get("status", "connecting"), 0)

                service_type = socket_info.get("service_type", "TCP")
                ip_address = socket_info.get("ip_address", "127.0.0.1")
                remote_port = socket_info.get("remote_port", 0)
                local_port = socket_info.get("local_port", 0)
                access_mode = socket_info.get("access_mode", 0)
                server_id = 0
                at_port = "usbmodem"

                resp += f'+QISTATE: {connect_id},"{service_type}","{ip_address}",{remote_port},{local_port},{socket_state},{context_id},{server_id},{access_mode},"{at_port}"\r\n'

            resp += "OK"
            return {"now": resp}
        except Exception as e:
            print(f"[QISTATE] Error in query_type=0: {e}")
            return {"now": "ERROR"}

    # AT+QISTATE=1,<connectID> (Query specific socket)
    if cmd.startswith("AT+QISTATE=1,"):
        try:
            connect_id = int(cmd.split("=")[1].split(",")[1])

            # Kontrola, zda socket existuje
            if connect_id not in global_state["sockets"]:
                return {"now": "ERROR"}

            socket_info = global_state["sockets"][connect_id]

            status_map = {
                "connecting": 1,
                "connected": 2,
                "listening": 3,
                "closing": 4,
                "failed": 0
            }
            socket_state = status_map.get(socket_info.get("status", "connecting"), 0)

            service_type = socket_info.get("service_type", "TCP")
            ip_address = socket_info.get("ip_address", "127.0.0.1")
            remote_port = socket_info.get("remote_port", 0)
            local_port = socket_info.get("local_port", 0)
            context_id = socket_info.get("context_id", 1)
            access_mode = socket_info.get("access_mode", 0)
            server_id = 0
            at_port = "usbmodem"

            resp = f'+QISTATE: {connect_id},"{service_type}","{ip_address}",{remote_port},{local_port},{socket_state},{context_id},{server_id},{access_mode},"{at_port}"\r\nOK'
            return {"now": resp}
        except Exception as e:
            print(f"[QISTATE] Error in query_type=1: {e}")
            return {"now": "ERROR"}

    # ---------------------------------------------------------
    # AT+QIOPEN  (otevření socketu)
    # ---------------------------------------------------------
    if cmd.startswith("AT+QIOPEN="):
        try:
            params = re.findall(r'"[^"]*"|[^,]+', cmd.split("=", 1)[1])
            params = [p.strip().strip('"') for p in params if p.strip()]
            if len(params) < 5:
                print("QIOPEN ERROR: málo parametrů", params)
                return {"now": "ERROR"}

            context_id = int(params[0])
            connect_id = int(params[1])
            service_type = params[2].upper()
            ip_address = params[3]
            remote_port = int(params[4])
            local_port = int(params[5]) if len(params) > 5 else 0
            access_mode = int(params[6]) if len(params) > 6 else 0

            if "sockets" not in global_state:
                global_state["sockets"] = {}

            if connect_id in global_state["sockets"]:
                print(f"QIOPEN ERROR: connect_id {connect_id} už existuje")
                return {"now": "ERROR"}

            # Uložení socketu do global_state
            global_state["sockets"][connect_id] = {
                "context_id": context_id,
                "service_type": service_type,
                "ip_address": ip_address,
                "remote_port": remote_port,
                "local_port": local_port,
                "access_mode": access_mode,
                "status": "connecting",
                "rx_buffer": b"",
                "tx_buffer": b"",
            }

            print(f"[QIOPEN] Opening socket: connect={connect_id}, service_type={service_type}, ip_address={ip_address}:{remote_port}")

            # SPUSTIT PARALELNÍ VLÁKNO PRO SOCKET (HNED, BEZ ČEKÁNÍ)
            socket_thread = threading.Thread(
                target=manage_socket,
                args=(connect_id, ip_address, remote_port, service_type),
                daemon=True
            )
            socket_thread.start()

            # Odpověď
            if access_mode == 2:
                return {"delay": 0.0, "response": "CONNECT"}
            else:
                urc_response = f'+QIOPEN: {connect_id},0'
                return {"delay": 0.0, "response": urc_response}

        except Exception as e:
            print(f"QIOPEN ERROR: {e}")
            import traceback
            traceback.print_exc()
            return {"now": "ERROR"}

    # ---------------------------------------------------------
    # AT+QISEND  (odeslání dat přes socket)
    # ---------------------------------------------------------
    if cmd.startswith("AT+QISEND="):
        try:
            params = cmd.split("=")[1].split(",")
            if len(params) >= 2:
                connect_id = int(params[0])
                send_length = int(params[1])

                # Kontrola, zda socket existuje
                if connect_id not in global_state["sockets"]:
                    print(f"[QISEND] ERROR: connect_id {connect_id} not found")
                    return {"now": "ERROR"}

                socket_info = global_state["sockets"][connect_id]

                # Pokud socket není connected, vrať ERROR
                if socket_info["status"] not in ("connected", "connecting"):
                    print(f"[QISEND] ERROR: socket {connect_id} status is {socket_info['status']}")
                    return {"now": "ERROR"}

                print(f"[QISEND] Ready for {send_length} bytes on socket {connect_id}")

                # Vrátit prompt '>' - AT thread pak zpracuje data
                return {
                    "delay": 0.1,
                    "response": ">",
                    "wait_for_data": True,
                    "connect_id": connect_id,
                    "send_length": send_length
                }
            else:
                return {"now": "ERROR"}
        except Exception as e:
            print(f"[QISEND] Exception: {e}")
            return {"now": "ERROR"}


    # ---------------------------------------------------------
    # AT+QICLOSE  (zavření socketu)
    # ---------------------------------------------------------
    if cmd.startswith("AT+QICLOSE="):
        try:
            connect_id = int(cmd.split("=")[1])

            # Kontrola, zda socket existuje
            if connect_id not in global_state["sockets"]:
                print(f"[QICLOSE] ERROR: connect_id {connect_id} not found")
                return {"now": "ERROR"}

            # Uzavření socketu
            try:
                if "socket" in global_state["sockets"][connect_id]:
                    global_state["sockets"][connect_id]["socket"].close()
            except:
                pass

            with mutex:
                del global_state["sockets"][connect_id]

            print(f"[QICLOSE] Socket {connect_id} closed and removed")

            return {"delay": 0.2, "response": "OK"}
        except Exception as e:
            print(f"[QICLOSE] Exception: {e}")
            return {"now": "ERROR"}

        # ---------------------------------------------------------
        # AT+QIRD  (čtení dat ze socketu)
        # ---------------------------------------------------------
    if cmd.startswith("AT+QIRD="):
        try:
            # Parsování: AT+QIRD=<connectID>[,<requestLength>]
            params = cmd.split("=")[1].split(",")
            connect_id = int(params[0])
            request_length = int(params[1]) if len(params) > 1 else 1500  # Default: 1500 bytů

            # Kontrola, zda socket existuje
            if connect_id not in global_state["sockets"]:
                return {"now": "ERROR"}

            socket_info = global_state["sockets"][connect_id]

            # Pokud socket není connected, vrať ERROR
            if socket_info.get("status") != "connected":
                return {"now": "ERROR"}

            with mutex:
                recv_buffer = socket_info.get("rx_buffer", b"")
                data_to_read = recv_buffer[:request_length]
                socket_info["rx_buffer"] = recv_buffer[request_length:]

            if not data_to_read:
                return {"now": "+QIRD: 0\r\n\r\nOK"}

            data_str = data_to_read.decode(errors='ignore')
            resp = f'+QIRD: {len(data_to_read)}\r\n{data_str}\r\n\r\nOK'
            return {"now": resp}


        except Exception as e:
            print(f"[QIRD] Error: {e}")
            return {"now": "ERROR"}

    # ---------------------------------------------------------
    # AT+QIRD=?  (testovací příkaz - seznam parametrů)
    # ---------------------------------------------------------
    if cmd == "AT+QIRD=?":
        return {"now": '+QIRD: (<connectID>),(<requestLength>)\r\nOK'}


# ---------------------------------------------------------
# VLÁKNO 1 – AT SOCKET (OPRAVENO)
# ---------------------------------------------------------
def at_thread():
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind(("127.0.0.1", AT_PORT))
    server.listen(1)
    print(f"[AT] Listening on port {AT_PORT}")

    while True:
        conn, addr = server.accept()
        print("[AT] Client connected:", addr)

        # Sledování stavu: čekáme na data pro QISEND/QISENDEX?
        send_wait_state = None  # {"connect_id": X, "send_length": Y}

        while True:
            try:
                data = conn.recv(1024)
                if not data:
                    break

                # Pokud čekáme na data z QISEND, zpracuj je
                if send_wait_state is not None:
                    connect_id = send_wait_state["connect_id"]
                    expected_len = send_wait_state["send_length"]

                    raw_data = data[:expected_len]
                    send_data = raw_data.decode(errors='ignore')

                    print(f"[AT] QISEND payload: {send_data}")

                    if connect_id not in global_state["sockets"]:
                        conn.sendall(b"ERROR\r\n")
                        send_wait_state = None
                        continue

                    socket_info = global_state["sockets"][connect_id]

                    if socket_info["status"] != "connected":
                        conn.sendall(b"ERROR\r\n")
                        send_wait_state = None
                        continue

                    sock = socket_info.get("socket")

                    if sock is None:
                        conn.sendall(b"ERROR\r\n")
                        send_wait_state = None
                        continue

                    service_type = socket_info.get("service_type")
                    ip_address = socket_info.get("ip_address")
                    remote_port = socket_info.get("remote_port")
                    bytes_sent = len(raw_data)

                    try:
                        # REAL SEND
                        if service_type == "UDP":
                            sock.sendto(raw_data, (ip_address, remote_port))
                        else:
                            sock.send(raw_data)

                        print(f"[QISEND] Sent {bytes_sent} bytes")

                        # TX statistics/debug
                        with mutex:
                            socket_info["tx_buffer"] += raw_data

                        conn.sendall(b"SEND OK\r\n")

                    except Exception as e:
                        print(f"[QISEND] Send failed: {e}")
                        conn.sendall(b"SEND FAIL\r\n")

                    send_wait_state = None
                    continue

                # Běžný AT příkaz
                cmd = data.decode().strip()
                print("[AT] Received:", cmd)

                result = evaluate_at_command(cmd)

                # Kontrola, jestli QISEND čeká na data
                if "wait_for_data" in result and result["wait_for_data"]:
                    send_wait_state = {
                        "connect_id": result["connect_id"],
                        "send_length": result["send_length"]
                    }

                if "ping_sequence" in result:
                    # HNED poslat OK
                    conn.sendall(b"OK\r\n\r\n")

                    params = result["ping_sequence"]
                    ip_address = params["ip_address"]
                    timeout = params["timeout"]
                    ping_num = params["ping_num"]

                    times = []
                    ttls = []
                    sent = ping_num
                    rcvd = 0
                    lost = 0
                    delay_step = 0.15  # zpoždění mezi odpověďmi v sekundách

                    for i in range(ping_num):
                        reply_time, ttl = get_ping_response(ip_address, timeout)
                        if reply_time is not None:
                            times.append(reply_time)
                            ttls.append(ttl)
                            rcvd += 1
                            resp = f'+QPING: 0,"{ip_address}",32,{reply_time},{ttl}'
                        else:
                            lost += 1
                            resp = f'+QPING: 0,"{ip_address}",32,{timeout},0'
                        schedule_response(conn, resp, delay=(i + 1) * delay_step)

                    # Statistika po posledním pingu
                    if times:
                        min_time = min(times)
                        max_time = max(times)
                        avg_time = sum(times) // len(times)
                    else:
                        min_time = max_time = avg_time = 0

                    stat_resp = f'+QPING: 0,{sent},{rcvd},{lost},{min_time},{max_time},{avg_time}'
                    schedule_response(conn, stat_resp, delay=(ping_num + 1) * delay_step)
                    continue  # přeskočte další zpracování, už jste naplánovali odpovědi

                with mutex:
                    if "now" in result:
                        conn.sendall((result["now"] + "\r\n").encode())
                    elif "delay" in result:
                        schedule_response(conn, result["response"], result["delay"])

            except Exception as e:
                print(f"[AT] Exception: {e}")
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
    threading.Thread(target=socket_worker, daemon=True).start()

    while True:
        time.sleep(1)

