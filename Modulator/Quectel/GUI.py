import tkinter as tk
from tkinter import messagebox, ttk
import socket
import json
import threading
import queue
#import pillow

# pro fungování obrázků v Tkinteru je potřeba nainstalovat Pillow: pip install Pillow
from PIL import Image, ImageTk

AT_IP = "127.0.0.1"
AT_PORT = 50000

SET_IP = "127.0.0.1"
SET_PORT = 65000

# ---------------------------------------------------------
# ODESLÁNÍ NASTAVENÍ (RSRP + BAND)
# ---------------------------------------------------------
def send_settings(rsrp_value, rssi_value, sinr_value, ber_value, band_value):
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.connect((SET_IP, SET_PORT))
        data = {"RSRP": rsrp_value, "RSSI": rssi_value, "SINR": sinr_value, "BER": ber_value, "band": band_value}
        sock.sendall(json.dumps(data).encode())
        sock.close()
    except Exception as e:
        messagebox.showerror("Chyba", f"Nepodařilo se odeslat nastavení:\n{e}")


# ---------------------------------------------------------
# FRONTA PRO BĚŽNÉ AT PŘÍKAZY (ASYNCHRONNÍ)
# ---------------------------------------------------------
at_queue = queue.Queue()


def at_worker():
    """Vlákno pro asynchronní zpracování běžných AT příkazů"""
    while True:
        cmd, callback = at_queue.get()
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.connect((AT_IP, AT_PORT))
            sock.sendall((cmd + "\n").encode())
            sock.settimeout(2)

            chunks = []
            while True:
                try:
                    data = sock.recv(4096)
                    if not data:
                        break
                    chunks.append(data.decode(errors="ignore"))
                except socket.timeout:
                    break

            sock.close()

            if not chunks:
                callback("(žádná odpověď)")
            else:
                callback("".join(chunks).strip())

        except Exception as e:
            callback(f"CHYBA spojení s emulátorem: {e}")
        at_queue.task_done()


# Spustit vlákno pro běžné příkazy
threading.Thread(target=at_worker, daemon=True).start()

def send_at_command(cmd, callback):
    """Asynchronní odeslání běžného AT příkazu"""
    at_queue.put((cmd, callback))



def send_qiopen_command(cmd, callback):
    """Vloží speciální příkaz do fronty (QIOPEN, QICLOSE, QISEND, QIRD)"""
    qiopen_queue.put((cmd, callback))

qiopen_queue = queue.Queue()

def qiopen_worker():
    while True:
        cmd, callback = qiopen_queue.get()
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.connect((AT_IP, AT_PORT))
            sock.sendall((cmd + "\n").encode())
            sock.settimeout(15)
            chunks = []
            while True:
                try:
                    data = sock.recv(4096)
                    if not data:
                        break
                    chunks.append(data.decode(errors="ignore"))
                except socket.timeout:
                    break
            if not chunks:
                callback("(žádná odpověď)")
            else:
                callback("".join(chunks).strip())
        except Exception as e:
            callback(f"CHYBA spojení s emulátorem: {e}")
        qiopen_queue.task_done()

threading.Thread(target=qiopen_worker, daemon=True).start()

# ---------------------------------------------------------
# GUI
# ---------------------------------------------------------
def main():
    root = tk.Tk()
    root.title("Emulátor modemu Quectel BG77 – GUI")
    root.geometry("1000x600")

    ram = ttk.Frame(root)
    ram.pack(fill="both", expand=True)

    # ---------------------------------------------------------
    # OKNO NASTAVENÍ
    # ---------------------------------------------------------
    def otevrit_nastaveni():
        if hasattr(otevrit_nastaveni, "okno") and otevrit_nastaveni.okno.winfo_exists():
            otevrit_nastaveni.okno.lift()
            return

        nastaveni = tk.Toplevel(root)
        nastaveni.title("Nastavení")
        nastaveni.geometry("800x600")
        nastaveni.resizable(False, False)
        otevrit_nastaveni.okno = nastaveni

        tk.Label(nastaveni, text="Síla signálu RSRP:", font=("Arial", 10)).place(x=150, y=60)
        RSRP = tk.Scale(nastaveni, from_=-140, to=-60, orient="horizontal")
        RSRP.set(-100)
        RSRP.place(x=150, y=80)

        tk.Label(nastaveni, text="RSSI:", font=("Arial", 10)).place(x=150, y=130)
        RSSI = tk.Scale(nastaveni, from_=-90, to=-60, orient="horizontal")
        RSSI.set(-80)
        RSSI.place(x=150, y=150)

        tk.Label(nastaveni, text="SINR:", font=("Arial", 10)).place(x=150, y=210)
        SINR = tk.Scale(nastaveni, from_=0, to=250, orient="horizontal")
        SINR.set(100)
        SINR.place(x=150, y=230)

        tk.Label(nastaveni, text="BER:", font=("Arial", 10)).place(x=150, y=290)
        BER = tk.Scale(nastaveni, from_=0, to=100, orient="horizontal")
        BER.set(100)
        BER.place(x=150, y=310)

        tk.Label(nastaveni, text="Číslo pásma (např. band 20):", font=("Arial", 10)).place(x=150, y=370)
        tk.Label(nastaveni,
                 text="Pásmo může nabývat hodnot pro GSM 900, 1800, 850 a 1900 MHz.\n Pro eMTC i NB-iOT je B1-5,B8, B12-B14, B18-B20, B25-B28, B31, B66,\n B72-73, B85. V NB-IoT není B14, B27 a navíc je tam B71.",
                 font=("Arial", 10)).place(x=60, y=390)

        cislo_pasma = tk.Entry(nastaveni, width=20)
        cislo_pasma.insert(0, "band 20")
        cislo_pasma.place(x=150, y=445)

        # ---- OBRÁZEK DESKY ----
        # Načtení a zmenšení obrázku
        img = Image.open("antena.jpg")  # Změňte na název vašeho souboru
        img = img.resize((200, 400))  # Přizpůsobte velikost dle potřeby
        img_tk = ImageTk.PhotoImage(img)

        # Vytvoření labelu s obrázkem
        obrazek_label = tk.Label(nastaveni, image=img_tk)
        obrazek_label.image = img_tk  # Udržet referenci!
        obrazek_label.place(x=540, y=60)  # Umístění vpravo nahoře pod lištu a nad odpovědi

        def ulozit():
            rsrp_value = RSRP.get()
            rssi_value = RSSI.get()
            sinr_value = SINR.get()
            ber_value = BER.get()
            band_value = cislo_pasma.get().strip()

            if not band_value:
                messagebox.showwarning("Chyba", "Zadej číslo pásma (např. band 20).")
                return

            send_settings(rsrp_value, rssi_value, sinr_value, ber_value, band_value)

            messagebox.showinfo(
                "Info",
                f"Nastavení odesláno do emulátoru.\r\n RSRP: {rsrp_value}\r\n RSSI: {rssi_value} \r\n SINR: {sinr_value} \r\n BER: {ber_value} \r\n Pásmo: {band_value}"
            )

            nastaveni.destroy()

        tk.Button(nastaveni, text="Uložit", command=ulozit).place(x=400, y=500)
        tk.Button(nastaveni, text="Zavřít", command=nastaveni.destroy).place(x=400, y=550)

    # Tlačítko Nastavení
    tk.Button(root, text="Nastavení", command=otevrit_nastaveni).place(x=50, y=20, anchor=tk.N)

    # ---------------------------------------------------------
    # AT PŘÍKAZY
    # ---------------------------------------------------------
    tk.Label(root, text="Vlož prosím AT příkaz:", font=("Arial", 10)).place(x=200, y=50, anchor=tk.N)
    vstup = tk.Entry(root, width=40)
    vstup.place(x=450, y=55, anchor=tk.N)

    # Výstupní okno
    ramecek = tk.LabelFrame(root, text="Odeslané příkazy a odpovědi", padx=5, pady=5)
    ramecek.pack(fill="both", expand=True, padx=20, pady=80)

    vystup = tk.Text(ramecek, wrap="word", height=10, state="disabled", font=("Arial", 10))
    vystup.pack(fill="both", expand=True)

    def log(text):
        vystup.config(state="normal")
        vystup.insert(tk.END, text + "\r\n")
        vystup.see(tk.END)
        vystup.config(state="disabled")

    def odeslat_vstup():
        cmd = vstup.get().strip()
        if not cmd:
            messagebox.showwarning("Chyba", "Zadej AT příkaz.")
            return

        log(f"{cmd}")  # HNED se zobrazí příkaz
        vstup.delete(0, tk.END)

        # Rozlišení mezi běžným a speciálním příkazem
        if cmd.startswith("AT+QI"):  # QIOPEN, QICLOSE, QISEND, QIRD
            send_qiopen_command(cmd, lambda resp: log(resp))  # Se zpožděním přijde odpověď
        else:
            send_at_command(cmd, lambda resp: log(resp))  # Se zpožděním přijde odpověď

    vstup.bind("<Return>", lambda event: odeslat_vstup())

    tk.Button(root, text="Odeslat", command=odeslat_vstup).place(x=700, y=50, anchor=tk.N)

    # Předdefinovaná tlačítka
    def odeslat_cmd(cmd):
        log(cmd)  # HNED se zobrazí příkaz
        send_at_command(cmd, lambda resp: log(resp))  # Se zpožděním přijde odpověď

    def odeslat_cmd_special(cmd):
        log(cmd)  # HNED se zobrazí příkaz
        send_qiopen_command(cmd, lambda resp: log(resp))  # Se zpožděním přijde odpověď

    tk.Button(ram, text="AT", command=lambda: odeslat_cmd("AT")).place(x=200, y=80, anchor=tk.N)
    tk.Button(ram, text="ATE", command=lambda: odeslat_cmd("ATE")).place(x=250, y=80, anchor=tk.N)
    tk.Button(ram, text="AT+QCSQ", command=lambda: odeslat_cmd("AT+QCSQ")).place(x=320, y=80, anchor=tk.N)
    tk.Button(ram, text="AT+CEREG?", command=lambda: odeslat_cmd("AT+CEREG?")).place(x=420, y=80, anchor=tk.N)

    # Další řada tlačítek
    tk.Button(ram, text="AT+CFUN?", command=lambda: odeslat_cmd("AT+CFUN?")).place(x=200, y=110, anchor=tk.N)
    tk.Button(ram, text='AT+CSQ', command=lambda: odeslat_cmd('AT+CSQ')).place(x=290, y=110, anchor=tk.N)
    tk.Button(ram, text="ATI", command=lambda: odeslat_cmd("ATI")).place(x=420, y=110, anchor=tk.N)
    tk.Button(ram, text="AT+GMI", command=lambda: odeslat_cmd("AT+GMI")).place(x=470, y=110, anchor=tk.N)

    # Třetí řada tlačítek
    tk.Button(ram, text="AT+GSN", command=lambda: odeslat_cmd("AT+GSN")).place(x=200, y=140, anchor=tk.N)
    tk.Button(ram, text="AT+GMM", command=lambda: odeslat_cmd("AT+GMM")).place(x=270, y=140, anchor=tk.N)
    tk.Button(ram, text="AT+CGMM", command=lambda: odeslat_cmd("AT+CGMM")).place(x=340, y=140, anchor=tk.N)
    tk.Button(ram, text="AT+CGMI", command=lambda: odeslat_cmd("AT+CGMI")).place(x=420, y=140, anchor=tk.N)

    # Čtvrtá řada tlačítek - SPECIÁLNÍ PŘÍKAZY S FRONTOU
    tk.Button(ram, text="AT+QIOPEN", command=lambda: odeslat_cmd_special('AT+QIOPEN=2,2,"TCP","62.245.74.185",7010')).place(
        x=200, y=170, anchor=tk.N)

    # toto asi nutno zakomentovat, pokud není, nainstalován Pilow, zobrazuje obrázek modemu i následující odstavec
    # ---- OBRÁZEK DESKY ----
    # Načtení a zmenšení obrázku
    img = Image.open("board.jpg")  # Změňte na název vašeho souboru
    img = img.resize((250, 200))  # Přizpůsobte velikost dle potřeby
    img_tk = ImageTk.PhotoImage(img)

    # Vytvoření labelu s obrázkem
    obrazek_label = tk.Label(root, image=img_tk)
    obrazek_label.image = img_tk  # Udržet referenci!
    obrazek_label.place(x=750, y=60)  # Umístění vpravo nahoře pod lištu a nad odpovědi

    root.mainloop()


if __name__ == "__main__":
    main()
