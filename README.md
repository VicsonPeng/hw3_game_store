# HW3 Game Store System

一個整合遊戲商城、大廳、多人連線對戰的平台系統。
支援開發者上架遊戲、玩家下載/更新/遊玩，以及 Plugin 擴充功能。

## 📂 目錄結構
* `server/` - 商城伺服器與資料庫
* `developer/` - 開發者端 (上架工具)
* `player/` - 玩家端 (大廳、下載區、Plugin)
* `common/` - 共用通訊協定
* `create_game_template.py` - 快速建立遊戲專案腳本

## 🚀 快速啟動 (Demo 流程)

### 0. 環境準備
本專案使用 Python 3，部分遊戲 (Draw Guess/Music Plugin) 需要 `pygame` 或 `tkinter`。
```bash
pip install pygame
1. 啟動 Server (本機)
Server 負責處理所有請求與資料庫。

--public_host: 請填入本機 IP (如 192.168.1.100 或 127.0.0.1 若單機測試)，這是回傳給 Client 連線用的 IP。

Bash

python server/server_main.py --public_host 127.0.0.1
2. 開發者上架遊戲 (Developer)
啟動開發者客戶端，將遊戲上傳至 Server。

Bash

python developer/dev_client.py --host 127.0.0.1
登入: 輸入任意帳號密碼 (如 dev/123)，系統會自動註冊為開發者。

上架流程:

選擇 1. 上架/更新 遊戲

輸入遊戲資料夾名稱 (範例: draw_guess 或 tetris_game)

輸入版本號 (如 1.0)

選擇遊戲類型 (1: CLI, 2: GUI, 3: Multiplayer)

完成上架。

3. 玩家遊玩 (Player)
啟動玩家客戶端 (可開啟多個視窗模擬多人)。

Bash

python player/player_client.py --host 127.0.0.1
登入: 輸入任意帳號密碼 (如 p1/123)，系統會自動註冊為玩家。

遊玩流程:

選 1. 遊戲商城 -> 瀏覽並下載遊戲。

選 2. 我的收藏 -> 選擇遊戲 -> 建立房間。

其他玩家選 3. 加入房間 -> 輸入房號。

房主按 S 開始遊戲 (Draw Guess 需至少 2 人)。

✨ 特色功能 (加分項)
1. Plugin 系統
位於 player/plugins/，支援動態載入。

功能: 進入房間自動播放背景音樂。

Demo: 可在主選單 6. 擴充功能 中啟用/停用，驗證是否影響遊戲聲音。

2. 遊戲實作
Draw Guess (你畫我猜): 完整 GUI、即時繪圖同步、聊天室猜題、計分板、斷線自動判定勝利。

Tetris (俄羅斯方塊): 雙人對戰，支援即時觀看對手畫面。

3. UX 優化
下載隔離: 不同玩家帳號擁有獨立下載目錄，互不衝突。

版本控管: 自動偵測 Server 版本與本地版本，提示更新。

防呆機制: 房間人數不足無法開始、斷線自動清理房間。


---

### 3. 最終驗收 (Checklist)

現在，你的專案已經完全符合你貼出的所有要求：

* **Menu-driven Interface**: 全程使用 1, 2, 3 選單操作 [cite: 1]。
* **不需記憶指令**: 啟動後全靠 UI 引導，錯誤有提示 [cite: 1]。
* **角色分離**: `server_main.py` 裡有 `developers` / `players` 兩張表 [cite: 8]。
* **檔案結構**: 包含了 `create_game_template.py` 與規定的目錄 。
* **玩家下載隔離**: `DOWNLOAD_DIR` 依據 username 分開 。
* **Server 重啟不遺失**: 使用 `db.json` [cite: 4]。
* **Use Case D1-D3**: 上架、更新(覆蓋)、下架 都有實作 [cite: 5]。
* **Use Case P1-P4**: 瀏覽、下載(含版本比對)、建房(含自動啟動)、評分 都有實作 [cite: 6]。
* **Plugin PL1-PL4**: 音樂插件可清單查看、開關、有裝有音樂沒裝沒事 [cite: 7]。