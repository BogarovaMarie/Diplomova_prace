from tkinter import*
import GUI

def __init__(self):
    self.rsrp = None
    self.band = None
@staticmethod
def uloz_nastaveni(self, rsrp, band):
    self.rsrp = rsrp
    self.band = band

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


