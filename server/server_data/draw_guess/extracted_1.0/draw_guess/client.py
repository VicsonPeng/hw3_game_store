import socket
import threading
import argparse
import tkinter as tk
from tkinter import messagebox

class DrawGameClient:
    def __init__(self, host, port, user):
        self.user = user
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.connect((host, port))
        self.sock.sendall(f"{user}\n".encode()) # Handshake

        self.root = tk.Tk()
        self.root.title(f"你畫我猜 - {user}")
        self.root.geometry("800x600")

        # 狀態
        self.is_drawer = False
        self.last_x = 0
        self.last_y = 0
        self.pen_color = "black"

        self.setup_ui()
        
        # 啟動網路監聽
        threading.Thread(target=self.network_loop, daemon=True).start()
        
        self.root.mainloop()

    def setup_ui(self):
        # 左側：畫布區
        left_frame = tk.Frame(self.root, width=600, height=600)
        left_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.info_label = tk.Label(left_frame, text="等待遊戲開始...", font=("Arial", 16), bg="#ddd", pady=5)
        self.info_label.pack(fill=tk.X)

        self.canvas = tk.Canvas(left_frame, bg="white", cursor="cross")
        self.canvas.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # 畫布事件綁定
        self.canvas.bind("<Button-1>", self.on_mouse_down)
        self.canvas.bind("<B1-Motion>", self.on_mouse_drag)

        # 顏色選擇 (只有畫家能用，但先顯示)
        btn_frame = tk.Frame(left_frame)
        btn_frame.pack(fill=tk.X, pady=5)
        colors = ["black", "red", "blue", "green", "orange"]
        for c in colors:
            btn = tk.Button(btn_frame, bg=c, width=3, command=lambda col=c: self.set_color(col))
            btn.pack(side=tk.LEFT, padx=2)
        
        self.clear_btn = tk.Button(btn_frame, text="清空", command=self.clear_canvas_action)
        self.clear_btn.pack(side=tk.RIGHT, padx=5)

        # 右側：聊天區
        right_frame = tk.Frame(self.root, width=200, bg="#f0f0f0")
        right_frame.pack(side=tk.RIGHT, fill=tk.Y)

        self.chat_log = tk.Text(right_frame, state='disabled', width=25)
        self.chat_log.pack(side=tk.TOP, fill=tk.BOTH, expand=True, padx=5, pady=5)

        self.chat_entry = tk.Entry(right_frame)
        self.chat_entry.pack(side=tk.BOTTOM, fill=tk.X, padx=5, pady=5)
        self.chat_entry.bind("<Return>", self.send_chat)

    def set_color(self, color):
        self.pen_color = color

    def clear_canvas_action(self):
        if self.is_drawer:
            self.canvas.delete("all")
            self.send_packet("CMD:CLEAR")

    def on_mouse_down(self, event):
        self.last_x = event.x
        self.last_y = event.y

    def on_mouse_drag(self, event):
        if not self.is_drawer:
            return
        
        # 畫線
        self.canvas.create_line(self.last_x, self.last_y, event.x, event.y, 
                                fill=self.pen_color, width=2, capstyle=tk.ROUND, smooth=True)
        
        # 傳送給 Server
        msg = f"D:{self.last_x},{self.last_y},{event.x},{event.y},{self.pen_color}"
        self.send_packet(msg)
        
        self.last_x = event.x
        self.last_y = event.y

    def send_chat(self, event):
        msg = self.chat_entry.get().strip()
        if msg:
            self.send_packet(f"CHAT:{msg}")
            self.chat_entry.delete(0, tk.END)

    def send_packet(self, msg):
        try:
            self.sock.sendall((msg + "\n").encode())
        except:
            print("Send failed")

    def log(self, msg, color="black"):
        self.chat_log.config(state='normal')
        self.chat_log.insert(tk.END, msg + "\n")
        self.chat_log.see(tk.END)
        self.chat_log.config(state='disabled')

    def network_loop(self):
        buffer = ""
        while True:
            try:
                data = self.sock.recv(4096).decode()
                if not data: break
                buffer += data
                while "\n" in buffer:
                    line, buffer = buffer.split("\n", 1)
                    self.process_server_msg(line.strip())
            except Exception as e:
                print(f"Network error: {e}")
                break

    def process_server_msg(self, line):
        if line.startswith("D:"):
            # 繪圖指令: D:x1,y1,x2,y2,color
            try:
                _, coords = line.split(":", 1)
                x1, y1, x2, y2, color = coords.split(",")
                self.canvas.create_line(float(x1), float(y1), float(x2), float(y2), 
                                        fill=color, width=2, capstyle=tk.ROUND, smooth=True)
            except: pass

        elif line.startswith("CHAT:"):
            _, user, msg = line.split(":", 2)
            self.log(f"{user}: {msg}")

        elif line.startswith("SYS:"):
            msg = line.split(":", 1)[1]
            self.log(f"系統: {msg}", "blue")

        elif line == "CMD:CLEAR":
            self.canvas.delete("all")

        elif line.startswith("CMD:YOUR_TURN:"):
            # 輪到我畫
            word = line.split(":", 2)[2]
            self.is_drawer = True
            self.info_label.config(text=f"輪到你了！請畫出：{word}", fg="red")
            self.log(f"--- 輪到你畫！題目: {word} ---", "red")

        elif line.startswith("CMD:GUESS_TURN:"):
            # 輪到我猜
            length = line.split(":", 2)[2]
            self.is_drawer = False
            self.info_label.config(text=f"猜猜看！單字長度: {length}", fg="black")
            self.log(f"--- 猜題時間 ---")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('--host', type=str, required=True)
    parser.add_argument('--port', type=int, required=True)
    parser.add_argument('--user', type=str, required=True)
    args, _ = parser.parse_known_args()

    DrawGameClient(args.host, args.port, args.user)