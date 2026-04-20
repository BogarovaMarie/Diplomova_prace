# vytvořit proměnnou frekvenční pásmo, kam se zapíše hodnota a zapíše se po potvrzení do Quectel
# pro GSM může nabývat hodnot viz vysledky


class ToolTip(object):
    def __init__(self, widget, text="info"):
        self.widget = widget
        self.text = text
        self.tipwindow = None
        widget.bind("<Enter>", self.show_tip)
        widget.bind("<Leave>", self.hide_tip)

    def show_tip(self, event=None):
        if self.tipwindow:
            return
        x = self.widget.winfo_rootx() + 20
        y = self.widget.winfo_rooty() + 20

        self.tipwindow = tw = tk.Toplevel(self.widget)
        tw.wm_overrideredirect(True)
        tw.wm_geometry(f"+{x}+{y}")

        label = tk.Label(
            tw,
            text=self.text,
            justify="left",
            background="#ffffe0",
            relief="solid",
            borderwidth=1,
            font=("Arial", 9)
        )
        label.pack(ipadx=5, ipady=3)

    def hide_tip(self, event=None):
        if self.tipwindow:
            self.tipwindow.destroy()
            self.tipwindow = None



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

    info_label = tk.Label(okno, text=" i ", fg="white", bg="blue", font=("Arial", 10, "bold"))
    info_label.place(x=380, y=140)

    ToolTip(info_label,
            text="Možné hodnoty:\n\n"
                 "GSM: 900, 1800 MHz\n"
                 "LTE: B1, B3, B7, B20\n"
                 "NR: n1, n3, n28, n78")