import os
import sys
import shutil

# 定義路徑
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATE_DIR = os.path.join(BASE_DIR, 'template')
GAMES_DIR = os.path.join(BASE_DIR, 'games')

def create_game(game_name):
    target_dir = os.path.join(GAMES_DIR, game_name)
    
    # 檢查是否已存在
    if os.path.exists(target_dir):
        print(f"[錯誤] 遊戲專案 '{game_name}' 已存在於 games/ 資料夾中。")
        return

    if not os.path.exists(TEMPLATE_DIR):
        print(f"[錯誤] 找不到範本資料夾: {TEMPLATE_DIR}")
        print("請確認是否已建立 developer/template/ 及相關檔案。")
        return

    try:
        # 1. 複製整個資料夾
        shutil.copytree(TEMPLATE_DIR, target_dir)
        
        # 2. 修改 config.json 中的遊戲名稱
        config_path = os.path.join(target_dir, 'config.json')
        with open(config_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        content = content.replace("{{GAME_NAME}}", game_name)
        
        with open(config_path, 'w', encoding='utf-8') as f:
            f.write(content)

        print(f"✅ 成功建立遊戲專案: {game_name}")
        print(f"📂 位置: {target_dir}")
        print("🚀 下一步：")
        print(f"   1. 編輯 {target_dir} 下的程式碼")
        print(f"   2. 執行 python developer/dev_client.py 上架遊戲")

    except Exception as e:
        print(f"[失敗] 建立過程中發生錯誤: {e}")
        # 清理失敗的資料夾
        if os.path.exists(target_dir):
            shutil.rmtree(target_dir)

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: python create_game_template.py <新遊戲名稱>")
    else:
        create_game(sys.argv[1])