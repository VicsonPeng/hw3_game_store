# client_gui.py
import socket
import threading
import json
import tkinter as tk
from common import send_json, recv_json, now_ms

CELL = 24
SMALL = 12

def parse_rle(rle):
    vals = []
    if not rle:
        return [[0]*10 for _ in range(20)]
    for chunk in rle.split(';'):
        try:
            v, c = chunk.split(':')
            v, c = int(v), int(c)
            vals.extend([v]*c)
        except Exception:
            pass
    if len(vals) < 200:
        vals += [0]*(200-len(vals))
    board = []
    k = 0
    for y in range(20):
        row = []
        for x in range(10):
            row.append(vals[k]); k+=1
        board.append(row)
    return board

class ClientGUI:
    def __init__(self, host, port, name, token, spectator=False):
        self.host = host
        self.port = port
        self.name = name
        self.token = token
        self.spectator = spectator
        self.sock = None
        self.root = tk.Tk()
        self.root.title(f"Tetris - {name}")
        self.canvas = tk.Canvas(self.root, width=10*CELL+220, height=20*CELL+20, bg="black")
        self.canvas.pack()
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        self.root.bind("<KeyPress>", self.on_key)
        self.my = {"board": [[0]*10 for _ in range(20)], "active": {"shape":"", "x":0, "y":0, "rot":0}, "score":0, "lines":0, "alive":True}
        self.op = {"board": [[0]*10 for _ in range(20)], "active": {"shape":"", "x":0, "y":0, "rot":0}, "score":0, "lines":0, "alive":True}
        self.running = True
        self.game_mode = "timer"
        self.game_duration = None  # 秒，只有 timer 用
        self.start_ms = now_ms()   # 開始時間，用來算經過秒數
        # 觀戰專用
        self.latest_players = []   # 存整包 SNAPSHOT players
        self.primary_idx = 0       # 0=第一個人放大, 1=第二個人放大
    
    def on_close(self):
        print("你已經離開遊戲")  # 終端機顯示提示
        self.running = False
        try:
            if self.sock:
                # 傳送 LEAVE 封包告訴 Server 我要走了
                send_json(self.sock, {"type": "LEAVE"})
                self.sock.close()
        except:
            pass
        self.root.destroy()  # 真正關閉視窗

    def draw_board(self, board, ox, oy, cell):
        for y in range(20):
            for x in range(10):
                v = board[y][x]
                if v:
                    self.canvas.create_rectangle(ox+x*cell, oy+y*cell, ox+(x+1)*cell-1, oy+(y+1)*cell-1, fill="#66ccff", outline="#222")
                else:
                    self.canvas.create_rectangle(ox+x*cell, oy+y*cell, ox+(x+1)*cell-1, oy+(y+1)*cell-1, outline="#222")

    def draw_active(self, active, ox, oy, cell):
        shape = active.get("shape","")
        if not shape: return
        rot = active.get("rot",0)
        x0 = active.get("x",0)
        y0 = active.get("y",0)
        SHAPES = {
            'I': [[(0,1),(1,1),(2,1),(3,1)],
                  [(2,0),(2,1),(2,2),(2,3)],
                  [(0,2),(1,2),(2,2),(3,2)],
                  [(1,0),(1,1),(1,2),(1,3)]],
            'O': [[(1,0),(2,0),(1,1),(2,1)]]*4,
            'T': [[(1,0),(0,1),(1,1),(2,1)],
                  [(1,0),(1,1),(2,1),(1,2)],
                  [(0,1),(1,1),(2,1),(1,2)],
                  [(1,0),(0,1),(1,1),(1,2)]],
            'S': [[(1,0),(2,0),(0,1),(1,1)],
                  [(1,0),(1,1),(2,1),(2,2)],
                  [(1,1),(2,1),(0,2),(1,2)],
                  [(0,0),(0,1),(1,1),(1,2)]],
            'Z': [[(0,0),(1,0),(1,1),(2,1)],
                  [(2,0),(1,1),(2,1),(1,2)],
                  [(0,1),(1,1),(1,2),(2,2)],
                  [(1,0),(0,1),(1,1),(0,2)]],
            'J': [[(0,0),(0,1),(1,1),(2,1)],
                  [(1,0),(2,0),(1,1),(1,2)],
                  [(0,1),(1,1),(2,1),(2,2)],
                  [(1,0),(1,1),(0,2),(1,2)]],
            'L': [[(2,0),(0,1),(1,1),(2,1)],
                  [(1,0),(1,1),(1,2),(2,2)],
                  [(0,1),(1,1),(2,1),(0,2)],
                  [(0,0),(1,0),(1,1),(1,2)]],
        }
        for (dx, dy) in SHAPES[shape][rot]:
            x = x0 + dx
            y = y0 + dy
            if 0 <= x < 10 and 0 <= y < 20:
                self.canvas.create_rectangle(ox+x*cell, oy+y*cell, ox+(x+1)*cell-1, oy+(y+1)*cell-1, fill="#ffdd66", outline="#222")

    def net_loop(self):
        try:
            self.sock = socket.create_connection((self.host, self.port), timeout=5)
            hello = {
                "type":"HELLO","version":1,"roomId":0,
                "userId":self.name,"roomToken":self.token,"name":self.name
            }
            if self.spectator:
                hello["role"] = "SPECTATOR"
            send_json(self.sock, hello)

            welcome = recv_json(self.sock)
            print("WELCOME:", welcome)

            # ← 這裡就把模式跟時間記起來
            self.game_mode = welcome.get('gameMode') or "timer"
            rules = welcome.get('rules') or {}
            self.game_duration = rules.get('durationSec')
            self.start_ms = now_ms()

            while self.running:
                msg = recv_json(self.sock)
                if not msg:
                    break

                if msg.get('type') == 'SNAPSHOT':
                    players = msg.get('players', [])
                    # 觀戰的話直接存起來，畫面再決定怎麼畫
                    if self.spectator:
                        self.latest_players = players
                    mine = None
                    other = None
                    for p in players:
                        if p['userId'] == self.name:
                            mine = p
                        else:
                            other = p
                    if mine is None and players:
                        mine = players[0]
                        other = players[1] if len(players)>1 else None
                    if mine:
                        self.my['board'] = parse_rle(mine['boardRLE'])
                        self.my['active'] = mine['active']
                        self.my['score'] = mine['score']
                        self.my['lines'] = mine['lines']
                        self.my['alive'] = mine['alive']
                    if other:
                        self.op['board'] = parse_rle(other['boardRLE'])
                        self.op['active'] = other['active']
                        self.op['score'] = other['score']
                        self.op['lines'] = other['lines']
                        self.op['alive'] = other['alive']
                if msg.get('type') == 'GAME_OVER':
                    # 印到 console（終端）
                    print("[GAME_OVER]", msg.get('message') or "", "winner=", msg.get('winner'))

                    # 顯示在 GUI（畫面中央）
                    self.running = False
                    text = msg.get('message') or f"GAME OVER\nWinner: {msg.get('winner')}"
                    self.canvas.delete("all")
                    self.canvas.create_text(10 + 5*CELL, 10 + 10*CELL,
                                            text=text, fill="white", font=("Arial", 16, "bold"))
                    # 2 秒後關閉視窗（想留著就移除下一行）
                    self.root.after(2000, self.root.destroy)
                    continue


        except Exception as e:
            print("Network error:", e)

    def on_key(self, ev):
        if self.spectator:
            key = ev.keysym.lower()
            if key in ('tab', 'slash'):   # 你也可以改成別的
                # 只有兩個人所以 0/1 互換
                self.primary_idx = 1 - self.primary_idx
            return  
        if not self.sock: return
        key = ev.keysym.lower()
        act = None
        if key in ('a','left'): act = 'LEFT'
        elif key in ('d','right'): act = 'RIGHT'
        elif key in ('w','up'): act = 'ROT'
        elif key in ('s','down'): act = 'SOFT'
        elif key in ('space',): act = 'HARDDROP'
        if act:
            try:
                send_json(self.sock, {"type":"INPUT","seq":0,"ts":now_ms(),"action":act})
            except Exception:
                pass

    def tick(self):
        self.canvas.delete("all")

        # 1) 顯示模式
        mode_txt = f"Mode: {self.game_mode}"
        if self.game_mode == "timer" and self.game_duration:
            mode_txt += f" ({self.game_duration}s)"
        self.canvas.create_text(10, 0, anchor='nw', fill="white", text=mode_txt)

        # 2) 顯示時間
        now = now_ms()
        elapsed = (now - self.start_ms) // 1000
        if self.game_mode == "timer" and self.game_duration:
            remain = self.game_duration - elapsed
            if remain < 0:
                remain = 0
            time_txt = f"Time: {remain}s"
        else:
            time_txt = f"Time: {elapsed}s"
        self.canvas.create_text(200, 0, anchor='nw', fill="white", text=time_txt)
        
        if self.spectator:
            # ---- 觀戰畫面 ----
            top_y = 40           # 棋盤從這裡往下畫
            big_x = 10           # 大盤的左上角 x
            if len(self.latest_players) >= 1:
                # 要放大的那位
                p_big = self.latest_players[self.primary_idx % len(self.latest_players)]
                name_big = p_big.get("userId", "player")
                board_big = parse_rle(p_big["boardRLE"])

                # 先畫名字，再畫大盤
                self.canvas.create_text(big_x, top_y - 18, anchor='nw', fill="white",
                                        text=f"{name_big}  (lines:{p_big['lines']}  score:{p_big['score']})")
                self.draw_board(board_big, big_x, top_y, CELL)
                self.draw_active(p_big["active"], big_x, top_y, CELL)

                # 另一位畫小的
                if len(self.latest_players) >= 2:
                    other_idx = 1 - (self.primary_idx % 2)
                    p_small = self.latest_players[other_idx]
                    name_small = p_small.get("userId", "player")
                    board_small = parse_rle(p_small["boardRLE"])

                    small_ox = 10 + 10*CELL + 20   # 右側一點
                    small_oy = top_y + 20          # 再往下一點，避免跟名字碰在一起
                    self.canvas.create_text(small_ox, small_oy - 18, anchor='nw', fill="white",
                                            text=f"{name_small}  (lines:{p_small['lines']})")
                    self.draw_board(board_small, small_ox, small_oy, SMALL)
                    self.draw_active(p_small["active"], small_ox, small_oy, SMALL)

            # 底下放提示
            self.canvas.create_text(10, 20*CELL+10, anchor='sw', fill="gray",
                                    text="(Press Tab to switch player)")

        else:
            # 原本的畫面
            self.draw_board(self.my['board'], 10, 10, CELL)
            self.draw_active(self.my['active'], 10, 10, CELL)
            self.canvas.create_text(10+10*CELL+10, 20, anchor='nw', fill="white",
                                    text=f"Me: {self.name}\nLines: {self.my['lines']}\nScore: {self.my['score']}")
            ox = 10+10*CELL+10
            oy = 100
            self.canvas.create_text(ox, oy-20, anchor='nw', fill="white", text="Opponent")
            self.draw_board(self.op['board'], ox, oy, SMALL)
            self.draw_active(self.op['active'], ox, oy, SMALL)
            if not self.my['alive']:
                self.canvas.create_text(10+5*CELL, 10+10*CELL, text="YOU TOPPED OUT", fill="red")
        self.root.after(100, self.tick)

    def run(self):
        threading.Thread(target=self.net_loop, daemon=True).start()
        self.tick()
        self.root.mainloop()

if __name__ == '__main__':
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument('--host', type=str, required=True)
    p.add_argument('--port', type=int, required=True)
    p.add_argument('--user', type=str, required=True)
    p.add_argument('--token', type=str, required=True)
    p.add_argument('--spectator', action='store_true')

    args = p.parse_args()
    ClientGUI(args.host, args.port, args.user, args.token, spectator=args.spectator).run()
