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
# [修正] 符合規格書的目錄名稱
GAMES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'games')

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
    username = input("Username: ")
    password = input("Password: ")
    
    send_json(client, {'command': 'LOGIN', 'payload': {'username': username, 'password': password, 'role': 'developer'}})
    resp = recv_json(client)
    print(f"Server: {resp['message']}")
    if resp['status'] != 'success':
        return

    while True:
        print("\n1. 上架/更新 遊戲 (Upload/Update Game)")
        print("2. 下架遊戲 (Remove Game)")
        print("3. 離開 (Exit)")
        choice = input("選擇: ")

        if choice == '1':
            # 列出目前 games 資料夾下的專案，方便選擇
            local_projects = [d for d in os.listdir(GAMES_DIR) if os.path.isdir(os.path.join(GAMES_DIR, d))]
            print(f"\n本地專案列表 ({GAMES_DIR}):")
            if not local_projects:
                print("(無專案，請先使用 create_game_template.py 建立)")
            else:
                for p in local_projects: print(f"- {p}")

            game_name = input("\n輸入遊戲名稱 (需與資料夾同名): ")
            version = input("輸入版本號 (例如 1.0): ")
            desc = input("輸入簡介: ")
            
            print("遊戲類型? (1: CLI, 2: GUI, 3: Multiplayer)")
            t_sel = input("選擇: ").strip()
            g_type = "GUI"
            if t_sel == '1': g_type = "CLI"
            elif t_sel == '3': g_type = "Multiplayer"
            
            # [修正] 改從 games/ 找
            game_path = os.path.join(GAMES_DIR, game_name)
            if not os.path.exists(game_path):
                print(f"[錯誤] 在 games/ 中找不到 '{game_name}'")
                continue

            config_data = update_config_version(game_path, version)
            min_players = 1
            if config_data and 'min_players' in config_data:
                min_players = config_data['min_players']

            print("正在打包遊戲...")
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
                print("正在上傳檔案...")
                if send_file(client, zip_path):
                    result = recv_json(client)
                    print(f"結果: {result['message']}")
                else:
                    print("上傳中斷或失敗")
                
                try: os.remove(zip_path)
                except: pass
            else:
                print(f"伺服器拒絕上傳: {ready.get('message') if ready else 'No response'}")
        
        elif choice == '2':
            game_name = input("輸入要下架的遊戲名稱: ")
            confirm = input(f"確定要下架 {game_name}? (y/n): ")
            if confirm.lower() == 'y':
                send_json(client, {
                    'command': 'REMOVE_GAME',
                    'payload': {'game_name': game_name}
                })
                result = recv_json(client)
                print(f"結果: {result.get('message')}")

        elif choice == '3':
            break

if __name__ == "__main__":
    main()