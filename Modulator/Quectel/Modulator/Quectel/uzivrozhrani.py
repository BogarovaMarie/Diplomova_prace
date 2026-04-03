import tkinter as tk
from tkinter import messagebox, ttk
import socket
import json

AT_IP = "127.0.0.1"
AT_PORT = 50000

SET_IP = "127.0.0.1"
SET_PORT = 65000


# ---------------------------------------------------------
# ODESLÁNÍ NASTAVENÍ (RSRP + BAND)
# ---------------------------------------------------------
def send_settings(rsrp_value, band_value):
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.connect((SET_IP, SET_PORT))
        data = {"rsrp": rsrp_value, "band": band_value}
        sock.sendall(json.dumps(data).encode())
        sock.close()
    except Exception as e:
        messagebox.showerror("Chyba", f"Nepodařilo se odeslat nastavení:\n{e}")


# ---------------------------------------------------------
# ODESLÁNÍ AT PŘÍKAZU
# ---------------------------------------------------------
def send_at_command(cmd):
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.connect((AT_IP, AT_PORT))
        sock.sendall((cmd + "\n").encode())

        sock.settimeout(2)
        data = sock.recv(4096)
        sock.close()

        if not data:
            return "(žádná odpověď)"

        return data.decode(errors="ignore").strip()

    except Exception as e:
        return f"CHYBA spojení s emulátorem: {e}"


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
        nastaveni.geometry("600x400")
        nastaveni.resizable(False, False)
        otevrit_nastaveni.okno = nastaveni

        tk.Label(nastaveni, text="Síla signálu RSRP:", font=("Arial", 10)).pack(pady=5)
        RSRP = tk.Scale(nastaveni, from_=-140, to=-60, orient="horizontal")
        RSRP.set(-100)
        RSRP.pack(pady=5)

        tk.Label(nastaveni, text="Číslo pásma (např. B20):", font=("Arial", 10)).pack(pady=5)
        cislo_pasma = tk.Entry(nastaveni, width=20)
        cislo_pasma.insert(0, "B20")
        cislo_pasma.pack(pady=5)

        def ulozit():
            rsrp_value = RSRP.get()
            band_value = cislo_pasma.get().strip()

            if not band_value:
                messagebox.showwarning("Chyba", "Zadej číslo pásma (např. B20).")
                return

            send_settings(rsrp_value, band_value)

            messagebox.showinfo(
                "Info",
                f"Nastavení odesláno do emulátoru.\nRSRP: {rsrp_value}\nPásmo: {band_value}"
            )

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
        vystup.insert(tk.END, text + "\n")
        vystup.see(tk.END)
        vystup.config(state="disabled")

    def odeslat_vstup():
        cmd = vstup.get().strip()
        if not cmd:
            messagebox.showwarning("Chyba", "Zadej AT příkaz.")
            return

        log(f"> {cmd}")
        response = send_at_command(cmd)
        log(f"< {response}")
        vstup.delete(0, tk.END)

    tk.Button(root, text="Odeslat", command=odeslat_vstup).place(x=700, y=50, anchor=tk.N)

    # Předdefinovaná tlačítka
    def odeslat_cmd(cmd):
        log(f"> {cmd}")
        response = send_at_command(cmd)
        log(f"< {response}")

    tk.Button(ram, text="AT", command=lambda: odeslat_cmd("AT")).place(x=200, y=80, anchor=tk.N)
    tk.Button(ram, text="ATE", command=lambda: odeslat_cmd("ATE")).place(x=250, y=80, anchor=tk.N)
    tk.Button(ram, text="AT+QCSQ", command=lambda: odeslat_cmd("AT+QCSQ")).place(x=320, y=80, anchor=tk.N)
    tk.Button(ram, text="AT+CEREG?", command=lambda: odeslat_cmd("AT+CEREG?")).place(x=420, y=80, anchor=tk.N)

    root.mainloop()


if __name__ == "__main__":
    main()
