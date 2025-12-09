import socket
import threading
import sys
import os
import json
import subprocess
import uuid
import zipfile
import random
import time
import argparse

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from common.utils import send_json, recv_json, recv_file, send_file

# 預設值，會被 args 覆蓋
HOST = '0.0.0.0' 
PORT = 5555
PUBLIC_HOST = '127.0.0.1'
MAX_ROOMS = 100

DB_FILE = 'server/db.json'
STORAGE_DIR = 'server/server_data'

db_lock = threading.Lock()

data_store = {
    "developers": {}, 
    "players": {},    
    "games": {},      
    "rooms": {},
    "user_history": {}
}
online_users = set()

def pick_free_port(start=10000, end=20000) -> int:
    for _ in range(50):
        p = random.randint(start, end)
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(('', p))
                return p
            except OSError:
                continue
    raise RuntimeError("No free port found")

def load_data():
    global data_store
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, 'r') as f:
                content = f.read()
                if content:
                    loaded = json.loads(content)
                    if "developers" not in loaded: loaded["developers"] = {}
                    if "players" not in loaded: loaded["players"] = {}
                    if "user_history" not in loaded: loaded["user_history"] = {}
                    data_store = loaded
        except Exception as e:
            print(f"[Warning] DB load failed: {e}, using empty DB")
    if not os.path.exists(STORAGE_DIR):
        os.makedirs(STORAGE_DIR)
    data_store['rooms'] = {}

def save_data():
    with db_lock:
        try:
            with open(DB_FILE, 'w') as f:
                save_dict = {
                    "developers": data_store.get("developers", {}),
                    "players": data_store.get("players", {}),
                    "user_history": data_store.get("user_history", {}),
                    "games": data_store.get("games", {}),
                    "rooms": {} 
                }
                json.dump(save_dict, f, indent=4)
        except Exception as e:
            print(f"[Error] Save DB failed: {e}")

def handle_client(conn, addr):
    print(f"[NEW CONNECTION] {addr} connected.")
    current_user = None
    current_role = None 

    # === [新增] 統一清理函式 ===
    def cleanup_user_session(user, role):
        if not user or not role: return
        
        # 1. 從線上名單移除 (使用正確的 session_id)
        session_id = f"{role}:{user}"
        if session_id in online_users:
            online_users.discard(session_id)
            print(f"[LOGOUT] {session_id} removed from online list.")

        # 2. 從所有房間移除 (僅限玩家)
        if role == 'player':
            for rid in list(data_store['rooms'].keys()):
                if rid in data_store['rooms']:
                    room = data_store['rooms'][rid]
                    if user in room['players']:
                        room['players'].remove(user)
                        # 如果房間空了，刪除房間
                        if not room['players']:
                            del data_store['rooms'][rid]
                            print(f"[Auto-Clean] Room {rid} deleted.")
    # ==========================
    
    try:
        while True:
            request = recv_json(conn)
            if not request:
                break
            
            cmd = request.get('command')
            payload = request.get('payload', {})
            response = {'status': 'error', 'message': 'Unknown command'}

            try:
                if cmd == 'LOGIN':
                    username = payload.get('username', '').strip()
                    password = payload.get('password', '').strip()
                    role = payload.get('role', 'player') 
                    
                    session_id = f"{role}:{username}"

                    if not username or not password:
                        response = {'status': 'fail', 'message': 'Empty username or password'}
                    elif session_id in online_users:
                        response = {'status': 'fail', 'message': f'Account ({role}) already logged in elsewhere.'}
                    else:
                        target_db = data_store["developers"] if role == 'developer' else data_store["players"]
                        
                        if username not in target_db:
                            target_db[username] = password
                            response = {'status': 'success', 'message': f'Registered as {role} and Logged in'}
                        elif target_db[username] == password:
                            response = {'status': 'success', 'message': f'Logged in as {role}'}
                        else:
                            response = {'status': 'fail', 'message': 'Wrong password'}
                    
                    if response['status'] == 'success':
                        current_user = username
                        current_role = role
                        online_users.add(session_id)
                        save_data()

                elif cmd == 'LOGOUT':
                    # === [修正] 呼叫統一清理 ===
                    cleanup_user_session(current_user, current_role)
                    # =========================
                    current_user = None
                    current_role = None
                    response = {'status': 'success'}

                elif cmd == 'LIST_USERS':
                    # 顯示純名字，隱藏 role 前綴
                    display_list = [sid.split(':')[1] for sid in online_users]
                    response = {'status': 'success', 'users': display_list}

                elif cmd == 'UPLOAD_GAME_INIT':
                    if not current_user or current_role != 'developer':
                        response = {'status': 'fail', 'message': 'Permission denied: Developer only'}
                    else:
                        game_name = payload.get('game_name')
                        version = payload.get('version', '1.0')
                        min_p = payload.get('min_players', 1)
                        g_type = payload.get('game_type', 'GUI') 
                        desc = payload.get('desc', '')

                        send_json(conn, {'status': 'ready_to_receive'})
                        file_info = recv_json(conn)
                        if file_info:
                            game_dir = os.path.join(STORAGE_DIR, game_name)
                            os.makedirs(game_dir, exist_ok=True)
                            save_path = os.path.join(game_dir, f"{version}.zip")
                            if recv_file(conn, save_path, file_info['size']):
                                old_reviews = data_store['games'].get(game_name, {}).get('reviews', [])
                                data_store['games'][game_name] = {
                                    'author': current_user,
                                    'version': version,
                                    'description': desc,
                                    'path': save_path,
                                    'reviews': old_reviews,
                                    'min_players': min_p,
                                    'game_type': g_type
                                }
                                save_data()
                                response = {'status': 'success', 'message': 'Upload complete'}
                            else:
                                response = {'status': 'fail', 'message': 'File receive failed'}
                        else:
                            response = {'status': 'fail', 'message': 'File info missing'}

                elif cmd == 'REMOVE_GAME':
                    if not current_user or current_role != 'developer':
                        response = {'status': 'fail', 'message': 'Permission denied: Developer only'}
                    else:
                        game_name = payload.get('game_name')
                        if game_name in data_store['games']:
                            if data_store['games'][game_name]['author'] == current_user:
                                del data_store['games'][game_name]
                                save_data()
                                response = {'status': 'success', 'message': 'Game removed'}
                            else:
                                response = {'status': 'fail', 'message': 'Permission denied: Not your game'}
                        else:
                            response = {'status': 'fail', 'message': 'Game not found'}

                elif cmd == 'LIST_GAMES':
                    summary = {}
                    for name, info in data_store['games'].items():
                        reviews = info.get('reviews', [])
                        avg = sum(r['score'] for r in reviews)/len(reviews) if reviews else 0
                        summary[name] = {
                            'version': info['version'], 
                            'author': info['author'],
                            'description': info['description'], 
                            'rating': round(avg, 1),
                            'min_players': info.get('min_players', 1),
                            'game_type': info.get('game_type', 'GUI')
                        }
                    response = {'status': 'success', 'games': summary}

                elif cmd == 'GET_GAME_DETAILS':
                    name = payload.get('game_name')
                    if name in data_store['games']:
                        g = data_store['games'][name]
                        response = {'status': 'success', 'game': {
                            'name': name, 'version': g['version'], 'author': g['author'],
                            'description': g['description'], 'reviews': g.get('reviews', []),
                            'min_players': g.get('min_players', 1),
                            'game_type': g.get('game_type', 'GUI')
                        }}
                    else:
                        response = {'status': 'fail', 'message': 'Game not found'}

                elif cmd == 'RATE_GAME':
                    if current_role != 'player':
                         response = {'status': 'fail', 'message': 'Only players can rate'}
                    else:
                        name = payload.get('game_name')
                        score = payload.get('score')
                        comment = payload.get('comment', '')

                        if not isinstance(score, int) or not (1 <= score <= 5):
                            response = {'status': 'fail', 'message': 'Score must be 1-5'}
                        elif len(comment) > 50:
                            response = {'status': 'fail', 'message': 'Comment too long'}
                        else:
                            history = data_store.get('user_history', {}).get(current_user, [])
                            if name not in history:
                                response = {'status': 'fail', 'message': 'You must play this game before rating!'}
                            elif name in data_store['games']:
                                review = {
                                    'user': current_user, 
                                    'score': score, 
                                    'comment': comment, 
                                    'time': time.time()
                                }
                                data_store['games'][name].setdefault('reviews', []).append(review)
                                save_data()
                                response = {'status': 'success', 'message': 'Review added'}
                            else:
                                response = {'status': 'fail', 'message': 'Game not found'}

                elif cmd == 'DOWNLOAD_GAME_INIT':
                    name = payload.get('game_name')
                    if name in data_store['games']:
                        send_json(conn, {'status': 'ready_to_send'})
                        send_file(conn, data_store['games'][name]['path'])
                        continue 
                    else:
                        response = {'status': 'fail', 'message': 'Game not found'}

                elif cmd == 'LIST_ROOMS':
                    rooms_info = {}
                    for rid in list(data_store['rooms'].keys()):
                        r = data_store['rooms'][rid]
                        rooms_info[rid] = {
                            'game_name': r['game_name'], 'host': r['host'],
                            'status': r['status'], 'players': r['players']
                        }
                    response = {'status': 'success', 'rooms': rooms_info}

                elif cmd == 'CREATE_ROOM':
                    if not current_user or current_role != 'player':
                        response = {'status': 'fail', 'message': 'Login as Player required'}
                    else:
                        name = payload.get('game_name')
                        if name not in data_store['games']:
                            response = {'status': 'fail', 'message': 'Game has been removed or not found'}
                        elif len(data_store['rooms']) >= MAX_ROOMS:
                            response = {'status': 'fail', 'message': 'Server room limit reached'}
                        else:
                            rid = str(len(data_store['rooms']) + 100)
                            data_store['rooms'][rid] = {
                                'host': current_user, 'game_name': name,
                                'players': [current_user], 'status': 'waiting',
                                'port': None, 'token': None,
                                'chat_history': [] 
                            }
                            response = {'status': 'success', 'room_id': rid}

                elif cmd == 'LOBBY_CHAT':
                    rid = payload.get('room_id')
                    msg = payload.get('message', '')
                    if rid in data_store['rooms'] and current_user:
                        chat_entry = f"[{current_user}]: {msg}"
                        data_store['rooms'][rid]['chat_history'].append(chat_entry)
                        if len(data_store['rooms'][rid]['chat_history']) > 50:
                            data_store['rooms'][rid]['chat_history'].pop(0)
                        response = {'status': 'success'}
                    else:
                        response = {'status': 'fail', 'message': 'Room not found'}

                elif cmd == 'JOIN_ROOM':
                    if not current_user or current_role != 'player':
                        response = {'status': 'fail', 'message': 'Login as Player required'}
                    else:
                        rid = payload.get('room_id')
                        if rid in data_store['rooms']:
                            room = data_store['rooms'][rid]
                            if room['status'] == 'playing':
                                response = {'status': 'fail', 'message': 'Game started'}
                            else:
                                if current_user not in room['players']:
                                    room['players'].append(current_user)
                                response = {'status': 'success', 'room_id': rid, 'game_name': room['game_name']}
                        else:
                            response = {'status': 'fail', 'message': 'Room not found'}

                elif cmd == 'GET_ROOM_INFO':
                    rid = payload.get('room_id')
                    if rid in data_store['rooms']:
                        r = data_store['rooms'][rid]
                        response = {
                            'status': 'success', 'room_status': r['status'],
                            'players': r['players'], 'host': r['host'],
                            'game_host': PUBLIC_HOST,
                            'game_port': r['port'],
                            'token': r['token'], 'game_name': r['game_name'],
                            'chat_history': r.get('chat_history', [])
                        }
                    else:
                        response = {'status': 'fail', 'message': 'Room closed'}

                elif cmd == 'LEAVE_ROOM':
                    rid = payload.get('room_id')
                    if rid in data_store['rooms']:
                        room = data_store['rooms'][rid]
                        if current_user in room['players']:
                            room['players'].remove(current_user)
                        if not room['players']:
                            del data_store['rooms'][rid]
                        elif current_user == room['host']:
                            room['host'] = room['players'][0]
                    response = {'status': 'success'}

                elif cmd == 'START_GAME':
                    rid = payload.get('room_id')
                    if rid in data_store['rooms']:
                        room = data_store['rooms'][rid]
                        game_name = room['game_name']
                        
                        # 記錄遊玩歷史
                        for p_name in room['players']:
                            if p_name not in data_store.get('user_history', {}):
                                data_store.setdefault('user_history', {})[p_name] = []
                            if game_name not in data_store['user_history'][p_name]:
                                data_store['user_history'][p_name].append(game_name)
                        save_data()

                        if current_user == room['host']:
                            try:
                                g_info = data_store['games'][game_name]
                                extract_dir = os.path.join(os.path.dirname(g_info['path']), f"extracted_{g_info['version']}")
                                if not os.path.exists(extract_dir):
                                    with zipfile.ZipFile(g_info['path'], 'r') as zf: zf.extractall(extract_dir)
                                
                                target = extract_dir
                                nested = os.path.join(extract_dir, game_name)
                                if os.path.exists(nested) and os.path.exists(os.path.join(nested, 'config.json')):
                                    target = nested
                                
                                with open(os.path.join(target, 'config.json')) as f:
                                    cfg = json.load(f)
                                
                                port = pick_free_port()
                                token = uuid.uuid4().hex[:16]
                                cmd_list = [sys.executable, cfg['server']['script']] + \
                                           cfg['server']['args_template'].format(
                                               port=port, token=token, room_id=rid,
                                               lobby_host=PUBLIC_HOST, lobby_port=PORT
                                           ).split()
                                
                                subprocess.Popen(cmd_list, cwd=target)
                                room['status'] = 'playing'
                                room['port'] = port
                                room['token'] = token
                                response = {'status': 'success'}
                            except Exception as e:
                                print(f"Start Game Error: {e}")
                                response = {'status': 'fail', 'message': f"Launch failed: {str(e)}"}
                        else:
                            response = {'status': 'fail', 'message': 'Only host can start'}
                    else:
                        response = {'status': 'fail', 'message': 'Room not found'}

            except Exception as inner_e:
                print(f"[Error processing command {cmd}]: {inner_e}")
                response = {'status': 'error', 'message': 'Internal Server Error'}

            send_json(conn, response)

    except Exception as e:
        print(f"[Connection Error]: {e}")
    finally:
        # === [修正] 呼叫統一清理 (確保斷線時也能清除房間狀態) ===
        cleanup_user_session(current_user, current_role)
        # =========================
        conn.close()

def start_server():
    parser = argparse.ArgumentParser(description='Game Store Server')
    parser.add_argument('--port', type=int, default=5555, help='Server listening port')
    parser.add_argument('--public_host', type=str, default='127.0.0.1', help='Public IP address')
    args = parser.parse_args()

    global PORT, PUBLIC_HOST
    PORT = args.port
    PUBLIC_HOST = args.public_host

    load_data()
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        server.bind((HOST, PORT))
    except OSError as e:
        print(f"Error binding to port {PORT}: {e}")
        return
    server.listen()
    
    # === [修正] 設定 Timeout 讓迴圈能響應 Ctrl+C ===
    server.settimeout(1.0) 
    # ============================================
    
    print(f"[LISTENING] Server is listening on 0.0.0.0:{PORT}")
    print(f"[CONFIG] Public Host (reported to clients): {PUBLIC_HOST}")
    print("Press Ctrl+C to stop server.")

    while True:
        try:
            try:
                # 嘗試接受連線，若 1秒內沒人連，會噴 socket.timeout
                conn, addr = server.accept()
            except socket.timeout:
                continue # 沒人連線，回到迴圈開頭 (這時會檢查 Ctrl+C)
            
            thread = threading.Thread(target=handle_client, args=(conn, addr))
            thread.daemon = True
            thread.start()
            
        except KeyboardInterrupt:
            print("\n[SHUTDOWN] Server stopping...")
            break
        except Exception as e:
            print(f"Accept Error: {e}")
            break
    
    server.close()

if __name__ == "__main__":
    start_server()