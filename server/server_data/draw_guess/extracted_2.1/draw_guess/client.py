import socket
import threading
import argparse
import tkinter as tk
from tkinter import messagebox
import json
import time

class GarticClient:
    def __init__(self, host, port, user):
        self.user = user
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            self.sock.connect((host, port))
            self.sock.sendall(f"{user}\n".encode())
        except:
            messagebox.showerror("Error", "無法連線到伺服器")
            return

        self.root = tk.Tk()
        self.root.title(f"Draw & Guess - {user}")
        self.root.geometry("1000x700")
        
        self.is_drawer = False
        self.pen_color = "black"
        self.pen_size = 3
        self.last_x, self.last_y = 0, 0
        
        self.setup_ui()
        
        self.running = True
        # 啟動網路監聽
        threading.Thread(target=self.network_loop, daemon=True).start()
        
        self.root.mainloop()

    def setup_ui(self):
        # 1. 頂部資訊列
        top_frame = tk.Frame(self.root, bg="#333", height=60)
        top_frame.pack(side=tk.TOP, fill=tk.X)
        
        self.lbl_word = tk.Label(top_frame, text="等待遊戲開始...", font=("Arial", 24, "bold"), bg="#333", fg="white")
        self.lbl_word.pack(side=tk.LEFT, padx=20, pady=10)
        
        self.lbl_timer = tk.Label(top_frame, text="--", font=("Arial", 24, "bold"), bg="#333", fg="#ff5555")
        self.lbl_timer.pack(side=tk.RIGHT, padx=20)

        # 2. 右側面板
        right_panel = tk.Frame(self.root, width=250, bg="#f0f0f0")
        right_panel.pack(side=tk.RIGHT, fill=tk.Y)
        
        tk.Label(right_panel, text="🏆 排行榜", font=("Arial", 12, "bold"), bg="#ddd").pack(fill=tk.X)
        self.rank_list = tk.Listbox(right_panel, height=8, font=("Arial", 11), bg="#f9f9f9", bd=0)
        self.rank_list.pack(fill=tk.X, padx=5, pady=5)
        
        tk.Label(right_panel, text="💬 聊天室", font=("Arial", 12, "bold"), bg="#ddd").pack(fill=tk.X)
        self.chat_log = tk.Text(right_panel, state='disabled', bg="white", font=("Arial", 10))
        self.chat_log.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        self.chat_log.tag_config("sys", foreground="blue")
        self.chat_log.tag_config("correct", foreground="green", font=("Arial", 10, "bold"))
        self.chat_log.tag_config("mine", foreground="#555")
        
        self.entry_chat = tk.Entry(right_panel, font=("Arial", 12))
        self.entry_chat.pack(fill=tk.X, padx=5, pady=10)
        self.entry_chat.bind("<Return>", self.send_chat)

        # 3. 左側工具列
        self.tool_frame = tk.Frame(self.root, bg="#444", width=60)
        self.tool_frame.pack(side=tk.LEFT, fill=tk.Y)
        
        colors = ["black", "red", "blue", "green", "yellow", "orange", "purple", "white"]
        for c in colors:
            btn = tk.Button(self.tool_frame, bg=c, width=3, height=1, 
                            command=lambda col=c: self.set_pen(col))
            btn.pack(pady=5, padx=5)
            
        tk.Label(self.tool_frame, text="Size", bg="#444", fg="white", font=("Arial", 8)).pack(pady=(10,0))
        self.scale_size = tk.Scale(self.tool_frame, from_=2, to=20, orient=tk.VERTICAL, bg="#444", fg="white", length=100, command=self.change_size)
        self.scale_size.set(3)
        self.scale_size.pack()
        
        tk.Button(self.tool_frame, text="CLR", bg="#ffcccc", command=self.clear_canvas).pack(side=tk.BOTTOM, pady=20, padx=5)

        # 4. 中央畫布
        self.canvas = tk.Canvas(self.root, bg="white", cursor="crosshair")
        self.canvas.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        self.canvas.bind("<Button-1>", self.on_mouse_down)
        self.canvas.bind("<B1-Motion>", self.on_mouse_drag)

    # === GUI 操作 ===
    
    def set_pen(self, color):
        self.pen_color = color
    
    def change_size(self, val):
        self.pen_size = int(val)

    def clear_canvas(self):
        if self.is_drawer:
            self.canvas.delete("all")
            self.sock.sendall(b"CLR\n")

    def on_mouse_down(self, event):
        self.last_x, self.last_y = event.x, event.y

    def on_mouse_drag(self, event):
        if not self.is_drawer: return
        self.draw_line(self.last_x, self.last_y, event.x, event.y, self.pen_color, self.pen_size)
        msg = f"D:{self.last_x},{self.last_y},{event.x},{event.y},{self.pen_color},{self.pen_size}\n"
        try: self.sock.sendall(msg.encode())
        except: pass
        self.last_x, self.last_y = event.x, event.y

    def draw_line(self, x1, y1, x2, y2, color, width):
        self.canvas.create_line(x1, y1, x2, y2, fill=color, width=width, capstyle=tk.ROUND, smooth=True)

    def send_chat(self, event):
        text = self.entry_chat.get().strip()
        if not text: return
        self.entry_chat.delete(0, tk.END)
        msg = json.dumps({"type": "CHAT", "data": text}) + "\n"
        try: self.sock.sendall(msg.encode())
        except: pass

    def log(self, text, tag=None):
        self.chat_log.config(state='normal')
        self.chat_log.insert(tk.END, text + "\n", tag)
        self.chat_log.see(tk.END)
        self.chat_log.config(state='disabled')

    # === 網路處理 (修正版: 使用 after 排程更新 GUI) ===

    def network_loop(self):
        buffer = ""
        while self.running:
            try:
                data = self.sock.recv(4096).decode()
                if not data: break
                buffer += data
                while "\n" in buffer:
                    line, buffer = buffer.split("\n", 1)
                    # 將封包處理交給主執行緒執行
                    self.root.after(0, self.process_packet, line.strip())
            except: break
        self.root.quit()

    def process_packet(self, line):
        if line.startswith("D:"):
            try:
                parts = line.split(":")
                args = parts[1].split(",")
                self.draw_line(float(args[0]), float(args[1]), float(args[2]), float(args[3]), args[4], int(args[5]))
            except: pass
            return
        
        if line == "CLR":
            self.canvas.delete("all")
            return

        try:
            msg = json.loads(line)
            mtype = msg.get("type")
            data = msg.get("data")
            
            if mtype == "SYS_MSG":
                self.log(f"[系統] {data}", "sys")
                
            elif mtype == "CHAT_MSG":
                self.log(f"{data['name']}: {data['text']}", "mine")
                
            elif mtype == "PHASE_SELECT":
                self.is_drawer = (data['drawer'] == self.user)
                self.lbl_word.config(text=f"畫家 {data['drawer']} 正在選詞...", fg="orange")
                self.canvas.delete("all")
                if not self.is_drawer:
                    self.log(f"--- 等待 {data['drawer']} 選詞 ---", "sys")

            elif mtype == "YOUR_SELECTION":
                self.prompt_selection(data['words'])

            elif mtype == "PHASE_DRAW":
                self.canvas.delete("all")
                self.start_timer(data['time'])
                if self.is_drawer:
                    self.log("--- 開始作畫！ ---", "sys")
                else:
                    self.lbl_word.config(text=data['mask'], fg="black")
                    self.log(f"--- 猜題開始！提示: {data['length']} 個字 ---", "sys")

            elif mtype == "YOUR_WORD":
                self.lbl_word.config(text=f"題目: {data}", fg="red")

            elif mtype == "UPDATE_HINT":
                if not self.is_drawer:
                    self.lbl_word.config(text=data)

            elif mtype == "CORRECT_GUESS":
                self.log(f"★ 恭喜你猜對了！(+{data['score']}分)", "correct")
                self.lbl_word.config(text="已猜對！等待回合結束...", fg="green")

            elif mtype == "PHASE_END":
                self.log(f"回合結束！答案是: {data['answer']}", "sys")
                self.lbl_word.config(text=f"答案: {data['answer']}", fg="blue")
                self.is_drawer = False

            elif mtype == "UPDATE_PLAYERS":
                self.update_rank(data)

        except Exception as e:
            print(f"Parse error: {e}")

    def prompt_selection(self, words):
        # 彈出視窗讓畫家選詞
        def ask():
            from tkinter import Toplevel, Label, Button
            
            top = Toplevel(self.root)
            top.title("選擇題目")
            top.geometry("300x150")
            top.grab_set() # 模態視窗，鎖定焦點
            
            Label(top, text="請選擇要畫的題目:", font=("Arial", 12)).pack(pady=10)
            
            def select(idx):
                msg = json.dumps({"type": "SELECT_WORD", "data": idx}) + "\n"
                self.sock.sendall(msg.encode())
                top.destroy()

            btn_frame = tk.Frame(top)
            btn_frame.pack(pady=5)
            
            # 顯示難度與題目
            diffs = ["簡單", "中等", "困難"]
            for i, w in enumerate(words):
                btn_text = f"{diffs[i]}: {w}"
                tk.Button(btn_frame, text=btn_text, command=lambda idx=i: select(idx)).pack(fill=tk.X, pady=2)

        # 確保在主執行緒執行
        self.root.after(100, ask)

    def update_rank(self, players):
        self.rank_list.delete(0, tk.END)
        for i, p in enumerate(players):
            icon = "✏️" if p.get('is_drawer') else f"{i+1}."
            self.rank_list.insert(tk.END, f"{icon} {p['name']} : {p['score']}")

    def start_timer(self, seconds):
        self.timer_val = seconds
        def tick():
            if self.timer_val > 0:
                self.timer_val -= 1
                self.lbl_timer.config(text=str(self.timer_val))
                self.root.after(1000, tick)
        tick()

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('--host', type=str, required=True)
    parser.add_argument('--port', type=int, required=True)
    parser.add_argument('--user', type=str, required=True)
    args, _ = parser.parse_known_args()

    GarticClient(args.host, args.port, args.user)