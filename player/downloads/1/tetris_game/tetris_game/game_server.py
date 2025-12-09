# game_server.py
import socket
import threading
import json
import time
import random
import sys
from collections import deque
from dataclasses import dataclass, field
from typing import List, Dict
from common import send_json, recv_json, now_ms

BOARD_W = 10
BOARD_H = 20

TETROMINOES = {
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

PIECES = ['I','O','T','S','Z','J','L']

def rle_encode_board(board: List[List[int]]) -> str:
    flat = []
    for y in range(BOARD_H):
        for x in range(BOARD_W):
            flat.append(board[y][x])
    res = []
    last = flat[0]
    count = 1
    for v in flat[1:]:
        if v == last:
            count += 1
        else:
            res.append(f"{last}:{count}")
            last = v
            count = 1
    res.append(f"{last}:{count}")
    return ';'.join(res)

def new_board() -> List[List[int]]:
    return [[0]*BOARD_W for _ in range(BOARD_H)]

def can_place(board, piece, rot, px, py) -> bool:
    for (dx, dy) in TETROMINOES[piece][rot]:
        x, y = px + dx, py + dy
        if x < 0 or x >= BOARD_W or y < 0 or y >= BOARD_H:
            return False
        if board[y][x] != 0:
            return False
    return True

def lock_piece(board, piece, rot, px, py, val):
    for (dx, dy) in TETROMINOES[piece][rot]:
        x, y = px + dx, py + dy
        if 0 <= x < BOARD_W and 0 <= y < BOARD_H:
            board[y][x] = val

def clear_lines(board) -> int:
    new_rows = [row for row in board if any(c==0 for c in row)]
    cleared = BOARD_H - len(new_rows)
    while len(new_rows) < BOARD_H:
        new_rows.insert(0, [0]*BOARD_W)
    for y in range(BOARD_H):
        board[y] = new_rows[y][:]
    return cleared

@dataclass
class PlayerState:
    name: str = ""
    board: List[List[int]] = field(default_factory=new_board)
    active_piece: str = ""
    rot: int = 0
    px: int = 3
    py: int = 0
    hold: str = ""
    nextq: deque = field(default_factory=deque)
    score: int = 0
    lines: int = 0
    level: int = 1
    alive: bool = True
    connected: bool = True
    sock: socket.socket = None

class GameServer:
    def __init__(self, host='0.0.0.0', port=15000, seed=12345,
                 room_id=0, token='', lobby_host='127.0.0.1', lobby_port=13000,
                 match_id='', mode='timer', duration_sec=120, target_lines=20):
        self.host = host
        self.spectators = set()
        self.port = port
        self.seed = seed
        self.room_id = room_id
        self.room_token = token
        self.lobby_host = lobby_host
        self.lobby_port = lobby_port
        self.start_ms = now_ms()                            # set early
        self.match_id = match_id or f"{room_id}-{self.start_ms}"
        self.mode = mode
        self.duration_ms = max(30, int(duration_sec)) * 1000
        self.target_lines = int(target_lines)
        self.gravity_ms = 700
        self.players = {}
        self.order = []
        self.lock = threading.Lock()
        random.seed(seed)
        self.running = True


    def bag_stream(self):
        while True:
            bag = PIECES[:]
            random.shuffle(bag)
            for p in bag:
                yield p

    def accept_players(self):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as srv:
            srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            srv.bind(('', self.port))
            srv.listen(16)  # 給多一點
            print(f"[GameServer] listening on")
            while self.running:
                s, addr = srv.accept()
                t = threading.Thread(target=self.handle_client, args=(s, addr), daemon=True)
                t.start()

    def spectator_reader(self, s):
        try:
            while self.running:
                msg = recv_json(s)
                if not msg:
                    break
        except Exception:
            pass
        finally:
            with self.lock:
                if s in self.spectators:
                    self.spectators.discard(s)
            try: s.close()
            except: pass

    def handle_client(self, s: socket.socket, addr):
        try:
            hello = recv_json(s)
            if not hello or hello.get('type') != 'HELLO' or hello.get('roomToken') != self.room_token:
                s.close()
                return
            
            is_spec = (hello.get('role') == 'SPECTATOR')
            name = hello.get('name', f"U{len(self.players)+1}")

            if is_spec:
                # 登記觀戰者，給一個簡單的 WELCOME，就不用塞方塊給他
                with self.lock:
                    self.spectators.add(s)
                send_json(s, {
                    "type": "WELCOME",
                    "role": "SPEC",
                    "gameMode": self.mode,
                    "rules": {
                        "durationSec": self.duration_ms // 1000 if self.mode == "timer" else None,
                        "targetLines": self.target_lines if self.mode == "lines" else None
                    }
                })
                # 觀戰者不需要 reader_loop，可以在這裡 return，讓接收走最外層的 recv-json？
                # 最簡單是開一個很空的 reader_loop，只是為了偵測斷線
                threading.Thread(target=self.spectator_reader, args=(s,), daemon=True).start()
                return
            
            with self.lock:
                if len(self.players) >= 2:
                    s.close()
                    return
                role = "P1" if len(self.players)==0 else "P2"
                st = PlayerState(name=name, sock=s)
                self.players[name] = st
                self.order.append(name)
            gen = self.bag_stream()
            for _ in range(5):
                st.nextq.append(next(gen))
            st.active_piece = st.nextq.popleft()
            st.rot = 0
            st.px, st.py = 3, 0
            if not can_place(st.board, st.active_piece, st.rot, st.px, st.py):
                st.alive = False
            send_json(s, {
                "type": "WELCOME",
                "role": role,
                "seed": self.seed,
                "bagRule": "7bag",
                # 新增：明確標示比賽模式與參數
                "gameMode": self.mode,  # "timer" | "survival" | "lines"
                "rules": {
                    "durationSec": self.duration_ms // 1000 if self.mode == "timer" else None,
                    "targetLines": self.target_lines if self.mode == "lines" else None
                },
                # 原本就有的重力節奏設定（保持 "fixed" 正確無誤）
                "gravityPlan": {"mode": "fixed", "dropMs": self.gravity_ms}
            })
            threading.Thread(target=self.reader_loop, args=(name, s), daemon=True).start()
        except Exception:
            try: s.close()
            except: pass

    def reader_loop(self, name, s):
        try:
            while self.running:
                msg = recv_json(s)
                if not msg:
                    break
                if msg.get('type') == 'INPUT':
                    act = msg.get('action')
                    with self.lock:
                        self.apply_action(self.players[name], act)
                elif msg.get('type') == 'LEAVE':
                    break

        except Exception:
            pass
        finally:
            with self.lock:
                if name in self.players:
                    self.players[name].connected = False  # 標記斷線
                    self.players[name].alive = False      # 視為死亡
            try: s.close()
            except: pass

    def apply_action(self, st: PlayerState, act: str):
        if not st.alive:
            return
        if act == 'LEFT':
            if can_place(st.board, st.active_piece, st.rot, st.px-1, st.py): st.px -= 1
        elif act == 'RIGHT':
            if can_place(st.board, st.active_piece, st.rot, st.px+1, st.py): st.px += 1
        elif act == 'ROT':
            nr = (st.rot + 1) % 4
            if can_place(st.board, st.active_piece, nr, st.px, st.py): st.rot = nr
        elif act == 'SOFT':
            self.gravity_tick(st)
        elif act == 'HARDDROP':
            while self.gravity_tick(st):
                pass

    def gravity_tick(self, st: PlayerState) -> bool:
        if not st.alive:
            return False
        if can_place(st.board, st.active_piece, st.rot, st.px, st.py+1):
            st.py += 1
            return True
        lock_piece(st.board, st.active_piece, st.rot, st.px, st.py, 1)
        cleared = clear_lines(st.board)
        if cleared:
            st.lines += cleared
            st.score += [0, 100, 300, 500, 800][cleared] if cleared <= 4 else 1200
        if len(st.nextq) < 3:
            for p in PIECES:
                st.nextq.append(p)
        nxt = st.nextq.popleft()
        st.active_piece = nxt
        st.rot = 0
        st.px, st.py = 3, 0
        if not can_place(st.board, st.active_piece, st.rot, st.px, st.py):
            st.alive = False
        return False

    def snapshot(self):
        res = []
        for name in self.order:
            st = self.players[name]
            res.append({
                "userId": name,
                "boardRLE": rle_encode_board(st.board),
                "active":{"shape": st.active_piece, "x": st.px, "y": st.py, "rot": st.rot},
                "hold": st.hold or "",
                "next": list(st.nextq)[:3],
                "score": st.score,
                "lines": st.lines,
                "level": st.level,
                "alive": st.alive,
            })
        return res 

    def broadcast(self, obj):
        obj["at"] = now_ms()
        for name, st in list(self.players.items()):
            s = st.sock
            try:
                send_json(s, obj)
            except Exception:
                pass
        for spec in list(self.spectators):
            try:
                send_json(spec, obj)
            except Exception:
                self.spectators.discard(spec)


    def run_loop(self):
        last_gravity = now_ms()
        last_snap = now_ms()
        reason, winner = None, None

        while self.running:
            now = now_ms()
            with self.lock:
                # 只有當遊戲已經有 2 人且開始後才檢查
                if len(self.players) == 2:
                    for name, st in self.players.items():
                        if not st.connected:
                            # 找到另一位玩家當作贏家
                            others = [n for n in self.players if n != name]
                            winner = others[0] if others else None
                            reason = "opponent_left"
                            break
            
            if reason: 
                break # 直接結束迴圈

            if now - last_gravity >= self.gravity_ms:
                with self.lock:
                    for name in self.order:
                        self.gravity_tick(self.players[name])
                last_gravity = now

            if now - last_snap >= 200:
                with self.lock:
                    snaps = self.snapshot()
                self.broadcast({"type":"SNAPSHOT","tick":now, "players": snaps})
                last_snap = now

            # --- termination checks ---
            with self.lock:
                ready = (len(self.players) == 2)
                alive_names = [n for n, st in self.players.items() if st.alive]
                alive_cnt = len(alive_names)

            if self.mode == 'timer':
                # 雙方都死 → 提前收尾（避免空轉到時間）
                if ready and alive_cnt == 0:
                    reason = "both_lose"
                    break
                # 時間到
                if now - self.start_ms >= self.duration_ms:
                    reason = "timeout"
                    break

            elif self.mode == 'survival':
                if ready:
                    if alive_cnt == 0:
                        reason = "both_lose"   # 同時頂滿
                        break
                    if alive_cnt == 1:
                        reason = "loss"        # 一人頂滿
                        break

            elif self.mode == 'lines':
                # 雙方都死 → 提前收尾
                if ready and alive_cnt == 0:
                    reason = "both_lose"
                    break
                # 有人達標
                with self.lock:
                    if any(st.lines >= self.target_lines for st in self.players.values()):
                        reason = "lines"
                        break
            # --- end termination checks ---


            time.sleep(0.01)

        self.running = False
        with self.lock:
            # compute results and winner
            results = [{"userId": n, "score": self.players[n].score, "lines": self.players[n].lines}
                    for n in self.order]

            def rank_key(name):
                st = self.players[name]
                return (st.lines, st.score)

            if self.mode == 'survival':
                alive = [n for n, st in self.players.items() if st.alive]
                winner = alive[0] if alive else max(self.players.keys(), key=rank_key)
            elif self.mode in ('timer','lines'):
                winner = max(self.players.keys(), key=rank_key) if self.players else None

        # notify clients
        # 建議放在 run_loop() 最後、report_to_lobby 之前
        msg = None
        if reason == "timeout":
            msg = f"時間到！以消行數決勝：{winner} 勝出"
        elif reason == "loss":
            msg = f"有人頂滿了！{winner} 勝出"
        elif reason == "lines":
            msg = f"達成目標行數！{winner} 勝出"
        elif reason == "both_lose":
            msg = f"雙方同時頂滿！以行數/分數決勝：{winner} 勝出"

        self.broadcast({
            "type": "GAME_OVER",
            "mode": self.mode,
            "reason": reason,
            "winner": winner,
            "results": results,
            "message": msg,          # ← 就是要給 Client 顯示的文字
            "at": now_ms()
        })


        # if you already implemented END_REPORT back to lobby, include mode/reason
        # try:
        #     self.report_to_lobby({"mode": self.mode, "reason": reason, "winner": winner, "results": results})
        # except Exception:
        #     pass


    def serve(self):
        threading.Thread(target=self.accept_players, daemon=True).start()
        self.run_loop()        

    def report_to_lobby(self, summary):
        import socket
        try:
            with socket.create_connection((self.lobby_host, self.lobby_port), timeout=3) as s:
                send_json(s, {
                    "type":"END_REPORT",
                    "roomId": self.room_id,
                    "matchId": self.match_id,
                    "users": list(self.players.keys()),
                    "startAt": self.start_ms,
                    "endAt": now_ms(),
                    "mode": self.mode,
                    "reason": summary.get("reason"),
                    "winner": summary.get("winner"),
                    "results": summary.get("results", [])
                })
                _ = recv_json(s)
        except Exception:
            pass



if __name__ == '__main__':
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument('--port', type=int, default=15000)
    p.add_argument('--seed', type=int, default=12345)
    p.add_argument('--room', type=int, default=1)
    p.add_argument('--token', type=str, required=True)
    p.add_argument('--lobby_host', type=str, default='127.0.0.1')
    p.add_argument('--lobby_port', type=int, default=13000)
    p.add_argument('--match_id',  type=str, default='')
    p.add_argument('--mode', type=str, default='timer', choices=['timer','survival','lines'])
    p.add_argument('--duration_sec', type=int, default=120)   # timer: >=30
    p.add_argument('--target_lines', type=int, default=20)    # lines: goal

    args = p.parse_args()

    gs = GameServer(
        port=args.port,
        seed=args.seed,
        room_id=args.room,
        token=args.token,
        lobby_host=args.lobby_host,
        lobby_port=args.lobby_port,
        match_id=args.match_id,
        mode=args.mode,
        duration_sec=args.duration_sec,
        target_lines=args.target_lines
    )
    gs.serve()

