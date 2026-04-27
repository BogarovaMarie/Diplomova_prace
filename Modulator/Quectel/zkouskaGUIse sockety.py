from tkinter import *
import socket
import threading
import json

REMOTE_IP = "127.0.0.1"
REMOTE_PORT = 65000

class App:
    def __init__(self, root):
        self.root = root
        root.title("Příjem RSRP")
        root.geometry("400x200")

        Label(root, text="Aktuální RSRP:", font=("Arial", 14)).pack(pady=10)
        self.rsrp_label = Label(root, text="---", font=("Arial", 20), fg="blue")
        self.rsrp_label.pack(pady=10)

        Label(root, text="Band:", font=("Arial", 14)).pack(pady=10)
        self.band_label = Label(root, text="---", font=("Arial", 18), fg="green")
        self.band_label.pack(pady=10)

        # Spuštění socket serveru ve vlákně
        threading.Thread(target=self.socket_server, daemon=True).start()

    def socket_server(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.bind((REMOTE_IP, REMOTE_PORT))
        sock.listen(5)
        print("Server listening on 127.0.0.1:65000")

        while True:
            conn, addr = sock.accept()
            print("Client connected:", addr)

            data = conn.recv(4096)
            if not data:
                conn.close()
                continue

            try:
                json_data = json.loads(data.decode())
                print("Přijatá data:", json_data)

                rsrp = json_data.get("rsrp", "---")
                band = json_data.get("band", "---")

                # Aktualizace GUI musí být přes .after()
                self.root.after(0, lambda: self.rsrp_label.config(text=str(rsrp)))
                self.root.after(0, lambda: self.band_label.config(text=str(band)))

            except Exception as e:
                print("Chyba JSON:", e)

            conn.close()


# Spuštění GUI
if __name__ == "__main__":
    root = Tk()
    app = App(root)
    root.mainloop()
