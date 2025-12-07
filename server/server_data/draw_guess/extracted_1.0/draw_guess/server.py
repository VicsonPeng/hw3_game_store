import socket
import threading
import argparse
import random
import time

# 題目庫
WORDS = ["apple", "book", "car", "dog", "egg", "fish", "ghost", "house", "ice", "jump", "kite", "lion", "moon", "nose"]

clients = []        # 存放所有連線 socket
players = {}        # socket -> username
lock = threading.Lock()

current_drawer = None   # 目前畫家的 socket
current_word = ""       # 目前題目
is_drawing = False      # 回合狀態

def broadcast(msg, exclude=None):
    """廣播訊息給所有人 (可排除發送者)"""
    with lock:
        for c in clients:
            if c != exclude:
                try:
                    c.sendall((msg + "\n").encode('utf-8'))
                except:
                    pass

def start_new_round():
    global current_drawer, current_word, is_drawing
    
    with lock:
        if not clients:
            return
        
        # 簡單輪替：隨機選一位 (或是你可以實作順序輪替)
        current_drawer = random.choice(clients)
        current_word = random.choice(WORDS)
        is_drawing = True
        drawer_name = players[current_drawer]

    print(f"New round: {drawer_name} drawing '{current_word}'")

    # 1. 通知所有人：新回合開始，清除畫布
    broadcast("CMD:CLEAR")
    broadcast(f"SYS:新回合開始！畫家是 [{drawer_name}]")

    # 2. 通知畫家：題目是什麼
    try:
        current_drawer.sendall(f"CMD:YOUR_TURN:{current_word}\n".encode())
    except:
        pass

    # 3. 通知其他人：正在等待
    broadcast(f"CMD:GUESS_TURN:{len(current_word)}", exclude=current_drawer)

def handle_client(conn, addr):
    global is_drawing
    print(f"New connection: {addr}")
    
    # 簡單握手：讀取名字
    try:
        name = conn.recv(1024).decode().strip()
        with lock:
            clients.append(conn)
            players[conn] = name
        
        broadcast(f"SYS:{name} 加入了房間！")
        
        # 如果是第一個人，自動開始
        if len(clients) >= 2 and not is_drawing:
            start_new_round()
        elif len(clients) == 1:
            conn.sendall("SYS:等待其他玩家加入...\n".encode())

        while True:
            data = conn.recv(1024)
            if not data: break
            
            # 處理黏包 (簡單處理，假設以 \n 分隔)
            buffer = data.decode()
            while "\n" in buffer:
                line, buffer = buffer.split("\n", 1)
                line = line.strip()
                if not line: continue

                # === 處理指令 ===
                
                # 1. 繪圖數據 (只有當前畫家能傳送)
                if line.startswith("D:") or line.startswith("CMD:CLEAR"):
                    if conn == current_drawer:
                        broadcast(line, exclude=conn) # 轉傳給其他人畫

                # 2. 聊天/猜題
                elif line.startswith("CHAT:"):
                    msg = line.split(":", 1)[1]
                    
                    # 檢查是否猜對 (畫家不能猜)
                    if conn != current_drawer and is_drawing and msg.lower() == current_word.lower():
                        broadcast(f"SYS:恭喜！ [{players[conn]}] 猜對了答案：{current_word}")
                        start_new_round()
                    else:
                        # 普通聊天訊息
                        broadcast(f"CHAT:{players[conn]}:{msg}")

    except Exception as e:
        print(f"Error: {e}")
    finally:
        with lock:
            if conn in clients:
                clients.remove(conn)
            if conn in players:
                del players[conn]
        
        conn.close()
        # 如果畫家走了，重開局
        if conn == current_drawer:
            broadcast("SYS:畫家離開了！重新開始回合...")
            start_new_round()

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, required=True)
    args, _ = parser.parse_known_args()

    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind(('0.0.0.0', args.port))
    server.listen()
    print(f"Draw & Guess Server running on port {args.port}")

    while True:
        conn, addr = server.accept()
        threading.Thread(target=handle_client, args=(conn, addr), daemon=True).start()

if __name__ == "__main__":
    main()