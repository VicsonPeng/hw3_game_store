import socket
import sys
import os
import json
import zipfile
import subprocess
import time
import threading
import importlib.util
import argparse

# 確保能 import common
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from common.utils import send_json, recv_json, recv_file

HOST = '127.0.0.1'
PORT = 5555
DOWNLOAD_DIR = 'player/downloads' # 初始值，會在 main 中依使用者更新
PLUGINS_DIR = 'player/plugins'
PLUGIN_CONFIG_FILE = os.path.join(PLUGINS_DIR, 'plugin_config.json')

# Socket 鎖，防止多執行緒競爭
client_lock = threading.Lock()

# === Helper Functions ===

def input_safe(prompt):
    """防止使用者直接按 Enter 或輸入空白"""
    while True:
        val = input(prompt).strip()
        if val: return val
        print("輸入不能為空，請重新輸入。")

def safe_request(client, req_data):
    """確保同一時間只有一個執行緒能使用 Socket"""
    with client_lock:
        if send_json(client, req_data):
            return recv_json(client)
    return None

def get_local_version(game_name):
    """讀取本地已安裝遊戲的版本號"""
    try:
        config_path = os.path.join(DOWNLOAD_DIR, game_name, game_name, 'config.json')
        if not os.path.exists(config_path):
            config_path = os.path.join(DOWNLOAD_DIR, game_name, 'config.json')
            
        if os.path.exists(config_path):
            with open(config_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return data.get('version', '0.0')
    except:
        pass
    return None

# === Plugin Management ===

def load_plugin_config():
    if os.path.exists(PLUGIN_CONFIG_FILE):
        try:
            with open(PLUGIN_CONFIG_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            return {}
    return {}

def save_plugin_config(config):
    try:
        with open(PLUGIN_CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=4)
    except Exception as e:
        print(f"[系統] 設定儲存失敗: {e}")

def list_plugins():
    if not os.path.exists(PLUGINS_DIR):
        os.makedirs(PLUGINS_DIR)
        default = os.path.join(PLUGINS_DIR, 'music_plugin.py')
        if not os.path.exists(default):
            with open(default, 'w', encoding='utf-8') as f:
                f.write("# Dummy music plugin code")

    config = load_plugin_config()
    plugins = []
    for f in os.listdir(PLUGINS_DIR):
        if f.endswith('.py') and f != '__init__.py':
            is_enabled = config.get(f, True)
            plugins.append({'filename': f, 'name': f, 'enabled': is_enabled})
    return plugins

def manage_plugins():
    while True:
        print("\n=== 🔌 擴充功能管理 (Plugin Manager) ===")
        current = list_plugins()
        if not current:
            print("(沒有偵測到任何插件檔案)")
        
        for i, p in enumerate(current):
            status = "[🟢 啟用中]" if p['enabled'] else "[🔴 已停用]"
            print(f"{i+1}. {p['name']} {status}")
        
        print("\n輸入編號切換狀態 (Enter 返回):")
        sel = input(">> ").strip()
        if not sel: break
        
        if sel.isdigit():
            idx = int(sel) - 1
            if 0 <= idx < len(current):
                target = current[idx]
                fname = target['filename']
                config = load_plugin_config()
                new_state = not target['enabled']
                config[fname] = new_state
                save_plugin_config(config)
                state_str = "啟用" if new_state else "停用"
                print(f"已{state_str} {fname}")
            else:
                print("無效的編號")
        else:
            print("請輸入數字")

def load_music_plugin():
    plugin_filename = 'music_plugin.py'
    plugin_path = os.path.join(PLUGINS_DIR, plugin_filename)
    if not os.path.exists(plugin_path): return None
    config = load_plugin_config()
    if not config.get(plugin_filename, True): return None

    try:
        spec = importlib.util.spec_from_file_location("music_plugin", plugin_path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    except Exception as e:
        print(f"[Plugin] 載入失敗: {e}")
    return None

# === Core Logic ===

def launch_game_client(game_name, username, game_host, game_port, token):
    try:
        game_dir = os.path.join(DOWNLOAD_DIR, game_name) 
        if not os.path.exists(game_dir):
            print(f"\n[錯誤] 尚未下載 ({game_name})")
            return False
        
        target = game_dir
        nested = os.path.join(game_dir, game_name)
        if os.path.exists(nested) and os.path.exists(os.path.join(nested, 'config.json')):
            target = nested
        
        cfg_path = os.path.join(target, 'config.json')
        if not os.path.exists(cfg_path):
            print(f"\n[錯誤] config.json 遺失")
            return False

        with open(cfg_path, 'r', encoding='utf-8') as f: config = json.load(f)
        
        script = config['client']['script']
        args = config['client']['args_template'].format(
            host=game_host, port=game_port, user=username, token=token
        )
        cmd = [sys.executable, script] + args.split()
        
        print(f"\n[系統] 啟動 {game_name} ...")
        subprocess.Popen(cmd, cwd=target)
        return True
    except Exception as e:
        print(f"\n[錯誤] 啟動異常: {e}")
        return False

def download_game_task(client, game_name):
    """下載遊戲並解壓縮"""
    try:
        print(f"\n[系統] 開始下載 '{game_name}' ...")
        
        with client_lock:
            if not send_json(client, {'command': 'DOWNLOAD_GAME_INIT', 'payload': {'game_name': game_name}}):
                print("[錯誤] 無法發送下載請求")
                return False
            
            resp = recv_json(client)
            if not resp or resp.get('status') != 'ready_to_send':
                print(f"[錯誤] 伺服器無法提供遊戲: {resp.get('message') if resp else 'No response'}")
                return False
            
            file_info = recv_json(client)
            filesize = file_info['size']
            
            save_path = os.path.join(DOWNLOAD_DIR, f"{game_name}.zip")
            os.makedirs(DOWNLOAD_DIR, exist_ok=True)
            
            if not recv_file(client, save_path, filesize):
                print("[錯誤] 下載過程中斷")
                return False
        
        with zipfile.ZipFile(save_path, 'r') as zip_ref:
            zip_ref.extractall(os.path.join(DOWNLOAD_DIR, game_name))
        
        try: os.remove(save_path)
        except: pass
        
        print(f"[系統] '{game_name}' 下載並安裝完成！")
        return True
    except Exception as e:
        print(f"[錯誤] 下載失敗: {e}")
        return False

def check_and_install(client, game_name, server_game_info=None):
    local_ver = get_local_version(game_name)
    
    if local_ver is None:
        print(f"\n[提示] 尚未安裝 '{game_name}'")
        if input("是否下載? (y/n): ").lower() == 'y':
            return download_game_task(client, game_name)
        return False

    if server_game_info:
        server_ver = server_game_info.get('version', '0.0')
        if server_ver > local_ver:
            print(f"\n[提示] '{game_name}' 有新版本！(本地: v{local_ver} -> 伺服器: v{server_ver})")
            if input("是否更新? (y/n): ").lower() == 'y':
                return download_game_task(client, game_name)
            else:
                print("[系統] 使用舊版本繼續...")
    return True

def room_lobby_loop(client, room_id, username):
    print(f"\n=== 進入房間 {room_id} ===")
    state = {'running': True, 'in_game': False}
    
    # 用來比對狀態差異
    last_room_state = {
        'players': [],
        'status': None,
        'host': None
    }

    # === Music Plugin ===
    music_plugin = load_music_plugin()
    music_player = None
    if music_plugin:
        try:
            music_player = music_plugin.create_music_player(room_id, username)
            music_player.start()
        except Exception as e:
            print(f"[Plugin] 啟動失敗: {e}")
            music_player = None

    def monitor():
        while state['running']:
            try:
                info = safe_request(client, {'command': 'GET_ROOM_INFO', 'payload': {'room_id': room_id}})
                if not info or info.get('status') != 'success':
                    if state['running']: 
                        # [修正] 直接插播通知
                        print("\n\n[系統警報] 房間已關閉或連線中斷！請按 Enter 離開...")
                        state['running'] = False
                    break
                
                # === [新增] 狀態變更偵測 (State Diff) ===
                current_players = info.get('players', [])
                current_status = info.get('room_status')
                current_host = info.get('host')
                
                has_change = False
                
                # 1. 偵測玩家變動
                if set(current_players) != set(last_room_state['players']):
                    print(f"\n\n[系統通知] 房間成員變動: {', '.join(current_players)} ({len(current_players)}人)")
                    has_change = True
                
                # 2. 偵測房主變動
                if current_host != last_room_state['host']:
                    print(f"\n\n[系統通知] 房主已變更為: {current_host}")
                    has_change = True

                # 3. 偵測遊戲開始
                if current_status == 'playing' and not state['in_game']:
                    print(f"\n\n[系統通知] 遊戲開始！正在啟動...")
                    state['in_game'] = True
                    if music_player: music_player.stop()
                    launch_game_client(info['game_name'], username, info['game_host'], info['game_port'], info['token'])
                    # 遊戲結束後，重印 Prompt
                    print("\n指令 [S:開始 / L:離開 / Enter:刷新] > ", end='', flush=True)

                # 更新快取
                last_room_state['players'] = current_players
                last_room_state['status'] = current_status
                last_room_state['host'] = current_host
                
                # 如果有變動，補印 Prompt，讓使用者知道還能輸入
                if has_change and state['running'] and not state['in_game']:
                    print("指令 [S:開始 / L:離開 / Enter:刷新] > ", end='', flush=True)
                # =======================================

                time.sleep(1)
            except Exception: break

    t = threading.Thread(target=monitor, daemon=True)
    t.start()

    try:
        # 初次顯示資訊
        # (稍等一下讓 monitor 抓第一次資料，避免顯示空的)
        time.sleep(0.5) 
        
        while state['running']:
            # 因為 Monitor 會負責印出變動，主迴圈只需要負責接收輸入
            # 這裡的 input 會阻塞，但 Monitor 會在背景持續運作並插播訊息
            cmd = input("指令 [S:開始 / L:離開 / Enter:刷新] > ").strip().upper()
            
            if not state['running']: break
            
            if cmd == 'S':
                gname = last_room_state.get('game_name') # 注意這裡改用 last_room_state 無法取得 game_name
                # 我們需要從 info 補抓 game_name，或者依賴 monitor 存下來
                # 簡單修正：直接發送 START，讓 Server 檢查
                # 若要做本地檢查，需讓 monitor 更新更多資料到外部變數
                
                # 為了簡化，這裡我們做基本的本地檢查 (利用 monitor 更新的變數)
                # 重新讀取 config 需要 gname，我們從 DOWNLOAD_DIR 找
                # 這邊稍微 tricky，因為 last_room_state 沒存 game_name
                # 但通常 create/join 時我們已知 game_name，可以傳進來，或是再次 request
                
                # 既然是 UX 優化，我們讓 Server 回傳錯誤訊息即可，Client 負責顯示
                resp = safe_request(client, {'command': 'START_GAME', 'payload': {'room_id': room_id}})
                if resp and resp['status'] != 'success': 
                    print(f"[錯誤] {resp.get('message')}")
            
            elif cmd == 'L':
                safe_request(client, {'command': 'LEAVE_ROOM', 'payload': {'room_id': room_id}})
                state['running'] = False; break
                
    except KeyboardInterrupt: state['running'] = False
    
    if music_player:
        music_player.stop()
    
    print("已退出房間。")

# === New Unified Menu System ===

def menu_game_center(client, username):
    """遊戲中心：整合商城、收藏、詳情"""
    while True:
        resp = safe_request(client, {'command': 'LIST_GAMES'})
        games = resp.get('games', {}) if resp else {}
        game_list = list(games.keys())

        print("\n=== 🎮 遊戲中心 (Game Center) ===")
        print(f"{'No.':<4} {'名稱':<15} {'類型':<8} {'狀態':<10} {'評分'}")
        print("-" * 60)
        
        for idx, name in enumerate(game_list):
            info = games[name]
            local_v = get_local_version(name)
            
            status = "未安裝"
            if local_v:
                status = "已安裝" if local_v >= info['version'] else "可更新"
            
            g_type = info.get('game_type', 'GUI')
            rating = f"⭐{info['rating']}"
            print(f"{idx+1:<4} {name:<15} {g_type:<8} {status:<10} {rating}")
        
        print("0. 返回主選單")
        sel = input("請選擇遊戲進入儀表板 (輸入 0 返回): ").strip()
        if sel == '0': break
        if not sel.isdigit() or int(sel) < 1 or int(sel) > len(game_list): continue
        
        target = game_list[int(sel)-1]
        action = menu_game_dashboard(client, target, games[target], username)
        
        if action == "CREATE":
            return action # 傳遞跳轉訊號
    return None

def menu_game_dashboard(client, game_name, info, username):
    """單一遊戲儀表板：下載、建房、評分都在這"""
    while True:
        local_v = get_local_version(game_name)
        status_text = "未安裝"
        action_btn = "下載遊戲"
        
        if local_v:
            if local_v < info['version']:
                status_text = f"可更新 (v{local_v} -> v{info['version']})"
                action_btn = "更新遊戲"
            else:
                status_text = f"已安裝 (v{local_v})"
                action_btn = "建立房間 (Play)"

        print(f"\n=== 🕹️ {game_name} 儀表板 ===")
        print(f"狀態: {status_text}")
        print(f"作者: {info['author']}")
        print(f"人數: {info['min_players']}+")
        print(f"簡介: {info['description']}")
        
        # 顯示評論
        resp = safe_request(client, {'command': 'GET_GAME_DETAILS', 'payload': {'game_name': game_name}})
        reviews = resp['game'].get('reviews', []) if resp else []
        if reviews:
            print(f"--- 玩家評價 ({len(reviews)}) ---")
            for r in reviews[-2:]:
                print(f"[{r['user']}] {r['score']}分: {r['comment']}")
        
        print("-" * 40)
        print(f"1. {action_btn}")  # 動態選項：下載 or 建立房間
        print("2. 評分與留言")
        if local_v: # 如果已安裝，額外顯示重新下載選項
            print("3. 強制重新下載")
        print("0. 返回列表")
        
        act = input("選擇: ").strip()
        
        if act == '1':
            if not local_v or local_v < info['version']:
                download_game_task(client, game_name)
            else:
                # 建立房間
                print(f"正在建立 {game_name} 房間...")
                resp = safe_request(client, {'command': 'CREATE_ROOM', 'payload': {'game_name': game_name}})
                if resp and resp['status'] == 'success':
                    # 設定全域變數或回傳 ID 讓 Main Loop 進入
                    global _TEMP_ROOM_ID
                    _TEMP_ROOM_ID = resp['room_id']
                    return "CREATE"
                else:
                    print(f"建立失敗: {resp.get('message') if resp else 'Error'}")

        elif act == '2':
            s = int(input("分數(1-5): "))
            c = input("評論: ")
            safe_request(client, {'command': 'RATE_GAME', 'payload': {'game_name': game_name, 'score': s, 'comment': c}})
            print("評分已送出")

        elif act == '3' and local_v:
            download_game_task(client, game_name)

        elif act == '0':
            break
    return None

# === Main ===

_TEMP_ROOM_ID = None # 用來傳遞建立成功的房號

def main():
    parser = argparse.ArgumentParser(description='Game Store Player Client')
    parser.add_argument('--host', type=str, required=True, help='Server IP address')
    parser.add_argument('--port', type=int, default=5555, help='Server port')
    args = parser.parse_args()

    global HOST, PORT
    HOST = args.host
    PORT = args.port

    client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try: client.connect((HOST, PORT))
    except: print(f"無法連線 {HOST}:{PORT}"); return

    print("=== Game Center Login ===")
    user = input_safe("Username: ")
    pwd = input_safe("Password: ")
    resp = safe_request(client, {'command': 'LOGIN', 'payload': {'username': user, 'password': pwd, 'role': 'player'}})
    if not resp or resp['status'] != 'success':
        print(f"登入失敗: {resp.get('message') if resp else 'Error'}")
        return
    
    # 隔離下載路徑
    global DOWNLOAD_DIR
    DOWNLOAD_DIR = os.path.join('player', 'downloads', user)
    if not os.path.exists(DOWNLOAD_DIR):
        os.makedirs(DOWNLOAD_DIR)
    print(f"Hi, {user}! (Save path: {DOWNLOAD_DIR})")

    while True:
        print(f"\n=== 主選單 ===")
        print("1. 瀏覽遊戲 (建房/管理/留言評分)")
        print("2. 👥 加入房間")
        print("3. 🌐 線上玩家")
        print("4. 🔌 擴充功能")
        print("0. 登出")
        
        choice = input(">> ").strip()
        
        if choice == '1':
            action = menu_game_center(client, user)
            if action == "CREATE" and _TEMP_ROOM_ID:
                room_lobby_loop(client, _TEMP_ROOM_ID, user)

        elif choice == '2':
            # 加入房間邏輯
            safe_request(client, {'command': 'LIST_GAMES'}) 
            resp = safe_request(client, {'command': 'LIST_ROOMS'})
            rooms = resp.get('rooms', {}) if resp else {}
            
            if not rooms:
                print("\n(目前沒有活躍的房間)")
                continue

            room_list = list(rooms.items())
            print("\n=== 活躍房間 ===")
            print(f"{'No.':<4} {'ID':<6} {'遊戲':<12} {'房主':<10} {'狀態'}")
            print("-" * 50)

            for idx, (rid, r_info) in enumerate(room_list):
                status = f"{len(r_info['players'])}人 {r_info['status']}"
                print(f"{idx+1:<4} {rid:<6} {r_info['game_name']:<12} {r_info['host']:<10} {status}")

            print("0. 返回")
            sel = input("\n選擇房間編號 (0 返回): ").strip()
            
            if sel == '0': continue
            if not sel.isdigit(): print("輸入錯誤"); continue
            
            sel_idx = int(sel) - 1
            if 0 <= sel_idx < len(room_list):
                target_rid, target_info = room_list[sel_idx]
                gname = target_info['game_name']
                print(f"\n[系統] 請求加入 {gname} (Room {target_rid})...")
                
                # 自動下載檢查
                # 這裡需要 info 才能比對版本，我們簡單再抓一次詳情
                det_resp = safe_request(client, {'command': 'GET_GAME_DETAILS', 'payload': {'game_name': gname}})
                g_info = det_resp['game'] if det_resp and det_resp['status']=='success' else None

                if check_and_install(client, gname, g_info):
                    resp = safe_request(client, {'command': 'JOIN_ROOM', 'payload': {'room_id': target_rid}})
                    if resp and resp['status'] == 'success':
                        room_lobby_loop(client, target_rid, user)
                    else:
                        print(f"加入失敗: {resp.get('message') if resp else 'Error'}")
            else:
                print("無效編號")

        elif choice == '3':
            resp = safe_request(client, {'command': 'LIST_USERS'})
            print(f"Online Users: {resp.get('users')}")
            
        elif choice == '4':
            manage_plugins()
            
        elif choice == '0':
            safe_request(client, {'command': 'LOGOUT'})
            break

if __name__ == "__main__":
    main()