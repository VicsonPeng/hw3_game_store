import socket
import threading
import argparse
import random
import time
import json

# 題目庫
WORD_POOL = {
    "EASY": ["Cat", "Sun", "Cup", "Hat", "Ball", "Tree", "Book", "Fish", "Star", "Eye"],
    "MEDIUM": ["Apple", "Pizza", "Ghost", "Robot", "Smile", "House", "Chair", "Clock", "Phone", "Beach"],
    "HARD": ["Dragon", "Guitar", "Planet", "Cactus", "Turtle", "Rocket", "Camera", "Spider", "Zombie", "Vampire"]
}

STATE_WAITING = 0
STATE_SELECTING = 1
STATE_DRAWING = 2
STATE_ROUND_END = 3

class GameServer:
    def __init__(self, port):
        self.port = port
        self.clients = []       
        self.players = {}       
        self.lock = threading.RLock()
        
        self.state = STATE_WAITING
        self.drawer = None      
        self.current_word = ""
        self.round_end_time = 0
        self.hint_indices = set()
        self.guessed_players = set()
        self.running = True

    def broadcast(self, msg_type, data, exclude=None):
        packet = json.dumps({"type": msg_type, "data": data}) + "\n"
        self._send_raw(packet, exclude)

    def broadcast_raw(self, raw_str, exclude=None):
        msg = raw_str + "\n"
        self._send_raw(msg, exclude)

    def _send_raw(self, msg, exclude):
        with self.lock:
            targets = list(self.clients)
        for c in targets:
            if c != exclude:
                try: c.sendall(msg.encode())
                except: pass

    def handle_client(self, conn, addr):
        print(f"Conn: {addr}")
        try:
            name = conn.recv(1024).decode().strip()
            color = "#%06x" % random.randint(0, 0xFFFFFF)
            
            with self.lock:
                self.clients.append(conn)
                self.players[conn] = {"name": name, "score": 0, "color": color}
            
            self.send_json(conn, "WELCOME", {"name": name, "color": color})
            self.broadcast_player_list()
            
            with self.lock:
                if self.state == STATE_WAITING:
                    print("First player joined, starting game immediately.")
                    self.start_selection_phase()
                elif self.state == STATE_SELECTING or self.state == STATE_DRAWING:
                    self.send_json(conn, "SYS_MSG", "遊戲進行中，請等待下一回合...")
                    if self.state == STATE_DRAWING:
                        mask = self.get_mask_str()
                        self.send_json(conn, "PHASE_DRAW", {
                            "time": int(self.round_end_time - time.time()),
                            "length": len(self.current_word),
                            "mask": mask
                        })

            while True:
                data = conn.recv(4096)
                if not data: break
                buffer = data.decode()
                while "\n" in buffer:
                    line, buffer = buffer.split("\n", 1)
                    line = line.strip()
                    if not line: continue
                    self.process_packet(conn, line)

        except Exception as e:
            print(f"Error {addr}: {e}")
        finally:
            self.disconnect_client(conn)

    def send_json(self, conn, mtype, data):
        try:
            packet = json.dumps({"type": mtype, "data": data}) + "\n"
            conn.sendall(packet.encode())
        except: pass

    def disconnect_client(self, conn):
        with self.lock:
            if conn in self.clients:
                self.clients.remove(conn)
                if conn in self.players:
                    name = self.players[conn]["name"]
                    del self.players[conn]
                    self.broadcast("SYS_MSG", f"{name} 離開了遊戲")
                    self.broadcast_player_list()
                
                # 如果畫家跑了：立刻重置，不要讓回合繼續
                if conn == self.drawer:
                    self.broadcast("ALERT", "畫家逃跑了！本回合無效，即將重新開始...")
                    self.force_stop_round()
                
                if not self.clients:
                    self.state = STATE_WAITING

    def process_packet(self, conn, line):
        if line.startswith("D:") or line.startswith("CLR"):
            if self.state == STATE_DRAWING and conn == self.drawer:
                self.broadcast_raw(line, exclude=conn)
            return

        try:
            msg = json.loads(line)
            mtype = msg.get("type")
            data = msg.get("data")

            if mtype == "CHAT":
                self.handle_chat(conn, data)
            elif mtype == "SELECT_WORD":
                if self.state == STATE_SELECTING and conn == self.drawer:
                    self.start_drawing_phase(data) 
        except: pass

    def handle_chat(self, conn, text):
        with self.lock:
            if conn not in self.players: return
            name = self.players[conn]["name"]
        
        if self.state == STATE_DRAWING and conn != self.drawer and conn not in self.guessed_players:
            if text.lower() == self.current_word.lower():
                time_left = max(1, int(self.round_end_time - time.time()))
                score_gain = int(time_left * 1.5) + 10
                
                with self.lock:
                    self.players[conn]["score"] += score_gain
                    if self.drawer in self.players:
                        self.players[self.drawer]["score"] += 5
                    self.guessed_players.add(conn)
                
                self.send_json(conn, "CORRECT_GUESS", {"score": score_gain})
                self.broadcast("SYS_MSG", f"★ {name} 猜對了答案！", exclude=conn)
                self.broadcast_player_list()
                
                with self.lock:
                    guessers_count = len(self.clients) - 1
                    if guessers_count > 0 and len(self.guessed_players) >= guessers_count:
                        threading.Thread(target=self.end_round, args=("所有人都猜對了！",)).start()
                return

        if conn in self.guessed_players:
            self.send_json(conn, "SYS_MSG", "你已經猜對了，請勿洩漏答案！")
        else:
            with self.lock:
                color = self.players[conn]["color"]
            self.broadcast("CHAT_MSG", {"name": name, "text": text, "color": color})

    # === 遊戲邏輯 ===

    def start_selection_phase(self):
        with self.lock:
            if not self.clients: 
                self.state = STATE_WAITING
                return
            
            # 輪替邏輯：確保選到存在的人
            # 建立一個安全的玩家列表
            valid_clients = list(self.clients)
            
            # 嘗試找下一個
            if self.drawer in valid_clients:
                idx = valid_clients.index(self.drawer)
                self.drawer = valid_clients[(idx + 1) % len(valid_clients)]
            else:
                # 如果上一局畫家不在了(或剛開始)，隨機選
                self.drawer = random.choice(valid_clients)
                
            self.state = STATE_SELECTING
            self.guessed_players = set()
            
            opts = [random.choice(WORD_POOL["EASY"]), 
                    random.choice(WORD_POOL["MEDIUM"]), 
                    random.choice(WORD_POOL["HARD"])]
            self.selection_opts = opts
            
            drawer_name = self.players[self.drawer]["name"]

        self.broadcast("PHASE_SELECT", {"drawer": drawer_name, "timeout": 10})
        self.send_json(self.drawer, "YOUR_SELECTION", {"words": opts})
        
        threading.Thread(target=self._timer_selection).start()

    def _timer_selection(self):
        time.sleep(10)
        with self.lock:
            if self.state == STATE_SELECTING:
                self.start_drawing_phase(0)

    def start_drawing_phase(self, word_idx):
        with self.lock:
            if self.state != STATE_SELECTING: return
            self.state = STATE_DRAWING
            try:
                self.current_word = self.selection_opts[int(word_idx)]
            except:
                self.current_word = self.selection_opts[0]
            
            self.round_end_time = time.time() + 60 
            self.hint_indices = set()
        
        mask = self.get_mask_str()
        
        self.broadcast("PHASE_DRAW", {
            "time": 60, 
            "length": len(self.current_word),
            "mask": mask
        })
        self.send_json(self.drawer, "YOUR_WORD", self.current_word)
        self.broadcast_raw("CLR")

        threading.Thread(target=self._game_loop_timer).start()

    def get_mask_str(self):
        display = []
        for i, char in enumerate(self.current_word):
            if i in self.hint_indices or char == ' ':
                display.append(char)
            else:
                display.append("_")
        return " ".join(display)

    def _game_loop_timer(self):
        start_t = time.time()
        hint_interval = 15 
        next_hint = start_t + hint_interval
        
        while self.state == STATE_DRAWING:
            now = time.time()
            if now >= self.round_end_time:
                self.end_round(f"時間到！答案是 {self.current_word}")
                break
            
            if now >= next_hint:
                self.reveal_hint()
                next_hint += hint_interval
                
            time.sleep(0.5)

    def reveal_hint(self):
        with self.lock:
            word_len = len(self.current_word)
            remain_idx = [i for i in range(word_len) if i not in self.hint_indices and self.current_word[i] != ' ']
            
            if not remain_idx or len(self.hint_indices) >= word_len // 2:
                return 
            
            idx = random.choice(remain_idx)
            self.hint_indices.add(idx)
            mask = self.get_mask_str()
            
        self.broadcast("UPDATE_HINT", mask)

    def force_stop_round(self):
        """畫家離開時強制重置"""
        with self.lock:
            self.state = STATE_ROUND_END
            self.broadcast_raw("CLR") # 清空畫面
        
        time.sleep(2) # 稍微喘息一下
        self.start_selection_phase() # 找新畫家

    def end_round(self, reason):
        with self.lock:
            if self.state == STATE_ROUND_END: return
            self.state = STATE_ROUND_END
        
        self.broadcast("PHASE_END", {"reason": reason, "answer": self.current_word})
        self.broadcast_player_list()
        
        time.sleep(5) 
        self.start_selection_phase() 

    def broadcast_player_list(self):
        lst = []
        with self.lock:
            for s, p in self.players.items():
                lst.append({"name": p["name"], "score": p["score"], "is_drawer": (s == self.drawer)})
        lst.sort(key=lambda x: x["score"], reverse=True)
        self.broadcast("UPDATE_PLAYERS", lst)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, required=True)
    args, _ = parser.parse_known_args()

    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind(('0.0.0.0', args.port))
    server.listen()
    print(f"Gartic-style Server running on {args.port}")

    game = GameServer(args.port)
    
    while True:
        try:
            conn, addr = server.accept()
            threading.Thread(target=game.handle_client, args=(conn, addr), daemon=True).start()
        except: break

if __name__ == "__main__":
    main()