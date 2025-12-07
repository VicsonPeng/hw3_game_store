import socket
import sys
import os
import shutil
import zipfile
import json  
import argparse

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from common.utils import send_json, recv_json, send_file

HOST = '127.0.0.1'
PORT = 5555
GAMES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'games')

# === Helper Functions ===

def get_valid_input(prompt, required=True):
    """
    通用輸入函式
    - 去除前後空白
    - 檢查必填
    - 支援輸入 'q' 取消
    """
    while True:
        val = input(prompt).strip()
        
        # 檢查取消
        if val.lower() == 'q':
            print("[動作已取消]")
            return None
        
        # 檢查必填
        if required and not val:
            print("⚠️ 此欄位為必填，請重新輸入 (或輸入 q 取消)")
            continue
            
        return val

def select_from_list(items, prompt_msg="請選擇編號"):
    """讓使用者從列表中輸入數字選擇"""
    if not items:
        print("(列表為空)")
        return None

    while True:
        choice = get_valid_input(f"{prompt_msg} (1-{len(items)}): ")
        if choice is None: return None # 取消
        
        if choice.isdigit():
            idx = int(choice) - 1
            if 0 <= idx < len(items):
                return items[idx]
            else:
                print("❌ 無效的編號")
        else:
            print("❌ 請輸入數字")

def zip_game(game_name, source_dir):
    output_filename = f"{game_name}.zip"
    with zipfile.ZipFile(output_filename, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for root, dirs, files in os.walk(source_dir):
            for file in files:
                file_path = os.path.join(root, file)
                arcname = os.path.relpath(file_path, os.path.dirname(source_dir))
                zipf.write(file_path, arcname)
    return output_filename

def update_config_version(game_dir, new_version):
    config_path = os.path.join(game_dir, 'config.json')
    if os.path.exists(config_path):
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            data['version'] = new_version
            with open(config_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=4, ensure_ascii=False)
            return data 
        except Exception as e:
            print(f"[警告] 無法自動更新 config.json: {e}")
    else:
        print(f"[警告] 找不到 {config_path}")
    return None

# === Main ===

def main():
    parser = argparse.ArgumentParser(description='Game Store Developer Client')
    parser.add_argument('--host', type=str, required=True, help='Server IP address')
    parser.add_argument('--port', type=int, default=5555, help='Server port')
    args = parser.parse_args()

    global HOST, PORT
    HOST = args.host
    PORT = args.port

    # 確保 games 資料夾存在
    if not os.path.exists(GAMES_DIR):
        os.makedirs(GAMES_DIR)

    client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        print(f"正在連線到 {HOST}:{PORT} ...")
        client.connect((HOST, PORT))
    except Exception:
        print(f"無法連線到 Server {HOST}:{PORT}")
        return

    print("=== Developer Client ===")
    username = get_valid_input("Username: ")
    if not username: return
    password = get_valid_input("Password: ")
    if not password: return
    
    send_json(client, {'command': 'LOGIN', 'payload': {'username': username, 'password': password, 'role': 'developer'}})
    resp = recv_json(client)
    print(f"Server: {resp['message']}")
    if resp['status'] != 'success':
        return

    while True:
        print("\n=== 開發者選單 ===")
        print("1. 上架/更新 遊戲 (Upload)")
        print("2. 下架遊戲 (Remove)")
        print("3. 離開 (Exit)")
        choice = input("選擇: ").strip()

        if choice == '1':
            # === 1. 列出本地專案供選擇 ===
            local_projects = [d for d in os.listdir(GAMES_DIR) if os.path.isdir(os.path.join(GAMES_DIR, d))]
            print(f"\n📂 本地專案列表 ({GAMES_DIR}):")
            if not local_projects:
                print("❌ 無專案，請先使用 create_game_template.py 建立")
                continue
            
            # 顯示編號
            for i, p in enumerate(local_projects):
                print(f"{i+1}. {p}")
            
            # 使用數字選擇
            game_name = select_from_list(local_projects, "請輸入專案編號")
            if not game_name: continue # 取消

            print(f"--> 已選擇: {game_name}")

            # === 2. 輸入版本與描述 (支援取消) ===
            version = get_valid_input("輸入版本號 (例如 1.0): ")
            if not version: continue

            desc = get_valid_input("輸入簡介 (選填, Enter跳過): ", required=False)
            if desc is None: continue # 輸入 q 取消
            
            # === 3. 選擇類型 ===
            print("遊戲類型?")
            print("1. CLI (純文字)")
            print("2. GUI (圖形介面)")
            print("3. Multiplayer (多人連線)")
            t_sel = get_valid_input("選擇類型 (1-3): ")
            if not t_sel: continue

            g_type = "GUI"
            if t_sel == '1': g_type = "CLI"
            elif t_sel == '3': g_type = "Multiplayer"
            
            # === 4. 開始處理 ===
            game_path = os.path.join(GAMES_DIR, game_name)
            
            # 更新 config
            config_data = update_config_version(game_path, version)
            min_players = 1
            if config_data and 'min_players' in config_data:
                min_players = config_data['min_players']

            print("📦 正在打包遊戲...")
            zip_path = zip_game(game_name, game_path)

            send_json(client, {
                'command': 'UPLOAD_GAME_INIT',
                'payload': {
                    'game_name': game_name, 'version': version, 'desc': desc, 
                    'min_players': min_players, 'game_type': g_type
                }
            })
            
            ready = recv_json(client)
            if ready and ready.get('status') == 'ready_to_receive':
                print("📤 正在上傳檔案...")
                if send_file(client, zip_path):
                    result = recv_json(client)
                    print(f"✅ 結果: {result['message']}")
                else:
                    print("❌ 上傳中斷或失敗")
                
                try: os.remove(zip_path)
                except: pass
            else:
                print(f"❌ 伺服器拒絕上傳: {ready.get('message') if ready else 'No response'}")
        
        elif choice == '2':
            # === 下架流程：先列出已上架的遊戲 ===
            print("\n🔄 正在查詢已上架遊戲...")
            send_json(client, {'command': 'LIST_GAMES'})
            resp = recv_json(client)
            games = resp.get('games', {})
            
            my_games = []
            print(f"\n🗑️  {username} 的上架列表:")
            for name, info in games.items():
                if info['author'] == username:
                    my_games.append(name)
            
            if not my_games:
                print("(您目前沒有上架任何遊戲)")
                continue

            # 顯示編號列表
            for i, name in enumerate(my_games):
                print(f"{i+1}. {name}")

            # 使用數字選擇
            target_game = select_from_list(my_games, "請輸入要下架的編號")
            if not target_game: continue

            # 確認
            confirm = get_valid_input(f"⚠️ 確定要下架 '{target_game}' 嗎? (輸入 y 確認): ")
            if confirm and confirm.lower() == 'y':
                send_json(client, {
                    'command': 'REMOVE_GAME',
                    'payload': {'game_name': target_game}
                })
                result = recv_json(client)
                print(f"結果: {result.get('message')}")
            else:
                print("[取消操作]")

        elif choice == '3':
            break

if __name__ == "__main__":
    main()