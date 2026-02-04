# vytvořit proměnnou frekvenční pásmo, kam se zapíše hodnota a zapíše se po potvrzení do Quectel
# pro GSM může nabývat hodnot viz vysledky



# proměnná typu IntVar → slider vrací celé číslo
aktualni_hodnota = tk.IntVar()

def slider_zmena(event):
    stitek_hodnota.config(text=f"Výkon přijatého referenčnho signálu (RSRP): {aktualni_hodnota.get():d}")

    slider = ttk.Scale(okno,
                       from_=-60, to=-120,
                       orient="horizontal",
                       variable=aktualni_hodnota,
                       command=slider_zmena)
    slider.place(x=200, y=140, anchor=tk.N)

    stitek_hodnota = tk.Label(okno, text="Výkon přijatého referenčního signálu (RSRP): -60")
    stitek_hodnota.place(x=200, y=170, anchor=tk.N)

