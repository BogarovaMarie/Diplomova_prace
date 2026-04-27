import tkinter as tk
from tkinter import messagebox, ttk
import socket
import json
import threading
import queue
#pro fungování obrázků v Tkinteru je potřeba nainstalovat Pillow: pip install Pillow
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
# FRONT QUEUE PRO AT PŘÍKAZY
# ---------------------------------------------------------
at_queue = queue.Queue()

def at_worker():
    while True:
        cmd, callback = at_queue.get()
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.connect((AT_IP, AT_PORT))
            sock.sendall((cmd + "\n").encode())
            sock.settimeout(4)
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

# Spustit vlákno pro zpracování fronty
threading.Thread(target=at_worker, daemon=True).start()

def send_at_command_async(cmd, callback):
    """Vloží AT příkaz do fronty, zpracuje jej worker vlákno."""
    at_queue.put((cmd, callback))
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
        nastaveni.geometry("400x600")
        nastaveni.resizable(False, False)
        otevrit_nastaveni.okno = nastaveni

        tk.Label(nastaveni, text="Síla signálu RSRP:", font=("Arial", 10)).pack(pady=5)
        RSRP = tk.Scale(nastaveni, from_=-140, to=-60, orient="horizontal")
        RSRP.set(-100)
        RSRP.pack(pady=5)

        tk.Label(nastaveni, text="RSSI:", font=("Arial", 10)).pack(pady=5)
        RSSI = tk.Scale(nastaveni, from_=-90, to=-60, orient="horizontal")
        RSSI.set(-80)
        RSSI.pack(pady=5)

        tk.Label(nastaveni, text="SINR:", font=("Arial", 10)).pack(pady=5)
        SINR = tk.Scale(nastaveni, from_=0, to=250, orient="horizontal")
        SINR.set(100)
        SINR.pack(pady=5)

        tk.Label(nastaveni, text="BER:", font=("Arial", 10)).pack(pady=5)
        BER = tk.Scale(nastaveni, from_=0, to=100, orient="horizontal")
        BER.set(100)
        BER.pack(pady=5)

        tk.Label(nastaveni, text="Číslo pásma (např. band 20):", font=("Arial", 10)).pack(pady=5)
        cislo_pasma = tk.Entry(nastaveni, width=20)
        cislo_pasma.insert(0, "band 20")
        cislo_pasma.pack(pady=5)

        # toto asi nutno zakomentovat, pokud není, nainstalován Pilow, zobrazuje obrázek modemu i následující odstavec
        # ---- OBRÁZEK DESKY ----
        # Načtení a zmenšení obrázku
        img = Image.open("vez.jpg")  # Změňte na název vašeho souboru
        img = img.resize((150, 100))  # Přizpůsobte velikost dle potřeby
        img_tk = ImageTk.PhotoImage(img)

        # Vytvoření labelu s obrázkem
        obrazek_label = tk.Label(root, image=img_tk)
        obrazek_label.image = img_tk  # Udržet referenci!
        obrazek_label.place(x=200, y=60)  # Umístění vpravo nahoře pod lištu a nad odpovědi

        def ulozit():
            rsrp_value = RSRP.get()
            rssi_value= RSSI.get()
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

        tk.Button(nastaveni, text="Uložit", command=ulozit).pack(pady=10)
        tk.Button(nastaveni, text="Zavřít", command=nastaveni.destroy).pack(pady=5)

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

        log(f"{cmd}") #smazáno /r/n
        vstup.delete(0, tk.END)

        # odpověď přijde později
        send_at_command_async(cmd, lambda resp: log(resp))

    vstup.bind("<Return>", lambda event: odeslat_vstup())

    tk.Button(root, text="Odeslat", command=odeslat_vstup).place(x=700, y=50, anchor=tk.N)

    # Předdefinovaná tlačítka
    def odeslat_cmd(cmd):
        log(cmd)
        send_at_command_async(cmd, lambda resp: log(resp))

    def odeslat_cmd_quiet(cmd):
        log(f"> {cmd}")
        send_at_command_async(cmd, lambda resp: log(resp))

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

    # Čtvrtá řada tlačítek
    tk.Button(ram, text="QIOPEN", command=lambda: odeslat_cmd_quiet('AT+QIOPEN=1,0,"TCP","127.0.0.1",8080')).place(x=200, y=170, anchor=tk.N)

    #toto asi nutno zakomentovat, pokud není, nainstalován Pilow, zobrazuje obrázek modemu i následující odstavec
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

#po QUIOPEN má ukazovat tento znak  log(f"> {cmd}")