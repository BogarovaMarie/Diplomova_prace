import tkinter as tk
from tkinter import messagebox
from tkinter import ttk
from tkinter import*
import Backend_Quectel_Server



#pouze okno pro zobrazeni akce, varování atd.
def kliknuti_na_tlacitko():
    """Zobrazovač událostí na kliknutí. Nastavení"""
    messagebox.showinfo("Nastavení", "Síla signálu (RSRP)")
    # Vytvoření popisku
  #  sila_signalu = tk.Label(okno, text="Síla signálu (RSRP)\n", font=("Arial", 12))
   # sila_signalu.pack(pady=20, side=LEFT)
    # Vytvoření popisku
    #bunka_identifikator = tk.Label(okno, text="\nIdentifikátor buňky", font=("Arial", 12))
    #bunka_identifikator.pack(pady=20, side=LEFT)

def main():
    # Vytvoří hlavní okno aplikace
    root = tk.Tk()
    root.title("Emulátor modemu Quectel BG77")
    root.geometry("1000x600")  # Šířka x Výška

    # Rám pro lepší uspořádání
    ram = ttk.Frame(root)
    ram.pack(fill="both", expand=True)

    def otevrit_nastaveni():
        """Otevře nové okno s nastavením."""
        # Pokud už okno existuje, neotevírat znovu
        if hasattr(otevrit_nastaveni, "okno") and otevrit_nastaveni.okno.winfo_exists():
            otevrit_nastaveni.okno.lift()  # Přenést dopředu
            return

        # Vytvoření nového okna
        nastaveni = tk.Toplevel(root)
        nastaveni.title("Nastavení")
        nastaveni.geometry("600x400")
        nastaveni.resizable(False, False)

        # Uložíme referenci, aby se neotevíralo vícekrát
        otevrit_nastaveni.okno = nastaveni

        # Label + Scale
        tk.Label(nastaveni, text="Síla signálu RSRP:", font=("Arial", 10)).pack(pady=5)
        RSRP = tk.Scale(nastaveni, from_=-60, to=-140, orient="horizontal")
        RSRP.pack(pady=5)

        # Label + Textové pole
        tk.Label(nastaveni, text="Pásmo může nabývat hodnot pro GSM 900, 1800, 850 a 1900 MHz. Pro eMTC i NB-iOT \n je B1-5,B8, B12-B14, B18-B20, B25-B28, B31, B66, B72-73, B85.\n V NB-IoT není B14, B27 a navíc je tam B71.", font=("Arial", 10)).pack(pady=5)

        # Label + Textové pole
        tk.Label(nastaveni, text="Číslo pásma", font=("Arial", 10)).pack(pady=5)
        cislo_pasma = tk.Entry(nastaveni, width=30)
        cislo_pasma.pack(pady=5)

        def ulozit():
            # uložíme hodnoty do instance Backend_Quectel_Server
            backend=Backend_Quectel_Server()
            backend.uloz_nastaveni(RSRP.get(), cislo_pasma.get())
            messagebox.showinfo(
                "Info",
                f"Nastavení uloženo\nRSRP: {backend.rsrp}\nČíslo pásma: {backend.band}"
            )

        tk.Button(nastaveni, text="Uložit", command=ulozit).pack(pady=5)
        tk.Button(nastaveni, text="Zavřít", command=nastaveni.destroy).pack(pady=5)


    # Create a button
    tlacitko_nastaveni = tk.Button(root, text="Nastavení", command=otevrit_nastaveni)
    tlacitko_nastaveni.place(x=50, y=20, anchor=tk.N)

    # Vytvoření popisku
    odpoved_tisk = tk.Label(root, text="Vlož prosím text k odeslání")
    odpoved_tisk.place(x=120, y=50, anchor=tk.N)

    # Textové pole
    vstup = tk.Entry(root, width=40)
    vstup.place(x=350, y=55, anchor=tk.N)

    def pridat_zpravu():
        """Přidá text z horního pole do spodního rámečku."""
        text = vstup.get().strip()  # vezme text a odstraní mezery na začátku/konci
        if not text:
            messagebox.showwarning("Prázdný vstup", "Zadejte prosím nějaký text.")
            return

        # Přidání textu do spodního textového pole
        vystup.config(state="normal")  # povolit úpravy
        vystup.insert(tk.END, text + "\n")  # přidat na konec
        response = Backend_Quectel_Server.get_odpoved(text)
        vystup.insert(tk.END, response + "\n")
        vystup.config(state="disabled")  # znovu zamknout
        vstup.delete(0, tk.END)  # vymazat horní pole

    # Vytvoření tlačítka
    tlacitko = tk.Button(root, text="Odeslat", command=pridat_zpravu)
    tlacitko.place(x=500, y=50, anchor=tk.N)

    # Rámeček pro spodní textové pole
    ramecek = tk.LabelFrame(root, text="Odeslané příkazy", padx=5, pady=5)
    ramecek.pack(fill="both", expand=True, padx=20, pady=20)

    # Spodní textové pole (jen pro čtení)
    vystup = tk.Text(ramecek, wrap="word", height=10, state="disabled", font=("Arial", 10))
    vystup.pack(fill="both", expand=True)

    # Univerzální funkce
    def pridat_prikaz(cmd):
        vystup.config(state="normal")
        vystup.insert(tk.END, cmd + "\n")
        response = Backend_Quectel_Server.get_odpoved(cmd)
        vystup.insert(tk.END, response + "\n")
        vystup.config(state="disabled")
        vstup.delete(0, tk.END)

#obsahuje cell iD
    tk.Button(ram, text="AT+CEREG?", command=lambda: pridat_prikaz("AT+CEREG?")).place(x=900, y=50, anchor=tk.N)

    #   AT + CGREG EGPRS Network Registration Status, AT + CREG existuje i toto
    # Funkce, která se spustí po kliknutí na tlačítko
    def pridat_AT():
        vystup.config(state="normal")  # povolit úpravy
        vystup.insert(tk.END, "AT" + "\n")  # přidat na konec
        response = Backend_Quectel_Server.get_odpoved("AT")
        vystup.insert(tk.END, response + "\n")
        vystup.config(state="disabled")  # znovu zamknout
        vstup.delete(0, tk.END)  # vymazat horní pole

    tlacitko2 = Button(ram, text="AT", command=pridat_AT)
    tlacitko2.place(x=700, y=50, anchor=tk.N)

    def pridat_ATE():
        vystup.config(state="normal")  # povolit úpravy
        vystup.insert(tk.END, "ATE" + "\n")  # přidat na konec
        response = Backend_Quectel_Server.get_odpoved("ATE")
        vystup.insert(tk.END, response + "\n")
        vystup.config(state="disabled")  # znovu zamknout
        vstup.delete(0, tk.END)  # vymazat horní pole

#echo
    tlacitko3 = Button(ram, text="ATE", command=pridat_ATE)
    tlacitko3.place(x=800, y=50, anchor=tk.N)

    tk.Button(ram, text="AT+QCSQ", command=lambda: pridat_prikaz("AT+QCSQ")).place(x=750, y=50, anchor=tk.N)

# AT+CSQ  Signal Quality Report AT+CSQ  RSSI Signal strength a BER

    #   AT + QCFG = "nwscanseq" Configure RAT Searching Sequence
    # AT + QCFG = "iotopmode" Configure Network Category to be Searched under LTE RAT
    # AT+QCSQ  Query and Report Signal Strength RSRP

    #   AT + QCFG = "band" Band Configuration
    # AT + QNWINFO Query Network Information
    #     AT + QCFG = "nb/bandprior" * Configure Band Scan Priority under NB - IoT
    # NB-IoT
    #  AT + QCFG = "nccconf" Configure NB - IoT Features

    #AT + COPS Operator Selection

    #AT + CEDRXS e - I - DRX Setting
    #AT + CEDRXRDP Read Dynamic Parameters

    #ECL level AT+QCFG="celevel" – některé verze firmware umožňují číst aktuální Coverage Enhancement Level., AT+QCFG="iotopmode" – nastavuje/čte režim (NB‑IoT, LTE‑M).

    # Spustí smyčku Thinker
    root.mainloop()

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"An error occurred: {e}")