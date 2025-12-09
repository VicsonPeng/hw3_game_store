# HW3 Game Store System

一個整合遊戲商城、大廳、多人連線對戰的平台系統。
支援開發者上架遊戲、玩家下載/更新/遊玩，以及 Plugin 擴充功能。

##  目錄結構
* `server/` - 商城伺服器與資料庫
* `developer/` - 開發者端 (上架工具)
* `player/` - 玩家端 (大廳、下載區、Plugin)
* `common/` - 共用通訊協定

##  快速啟動 (Demo 流程)

### 0. 環境準備
本專案使用 Python 3，部分遊戲 (Draw Guess/Music Plugin) 需要 `tkinter`。
直接`git clone`完整份專案

### 1. 啟動 Server (本機)
Server 負責處理所有請求與資料庫。
* cd至clone下來的資料夾後，把server與common資料夾放入遠端資料夾`112550128_hw3`中
```
scp -r server common [user_name]@linux[1-4].cs.nycu.edu.tw:~/112550128_hw3/
```
，連線至遠端(linux)，進入`112550128_hw3`並執行
```
python server/server_main.py
```

### 2. 開發者上架遊戲 (Developer)
啟動開發者客戶端，將遊戲上傳至 Server。

在本地端執行
```
python developer/dev_client.py --host 140.113.17.1[1-4]
```
* 1-4取決於linux1-4

* **登入**: 輸入任意帳號密碼 (如 `dev`/`123`)，系統會自動註冊為開發者。
* **上架流程**:
    1.  選擇 `1. 上架/更新 遊戲`。
    2.  選擇要上架的專案 (例如 `draw_guess` 或 `tetris_game`)。
    3.  輸入版本號 (如 `1.0`) 與類型 (CLI/GUI/Multiplayer(不能單人遊玩))。
    4.  系統會自動打包並上傳至 Server。

### 3. 啟動 Player Client (本地)
玩家負責遊玩。可開啟多個終端機模擬多人連線。

在本地端執行
```
python player/player_client.py --host 140.113.17.1[1-4]
```
* 1-4取決於linux1-4

* **登入**: 輸入任意帳號 (如 `p1`/`123`)，自動註冊為玩家。
* **下載路徑**: 每個玩家的下載內容會隔離在 `player/downloads/{username}/`，互不衝突。
* **遊玩流程**:
    1.  **商城**: 瀏覽並下載遊戲 (支援版本比對，舊版會提示更新)。
    2.  **收藏**: 選擇已下載遊戲 -> 建立房間。
    3.  **加入**: 其他玩家輸入房號加入。
    4.  **開始**: 房主按 `Start` (系統會檢查 `min_players` 人數限制)。

### 4. 幫助developer開發
執行
```
python developer/create_game_template.py [game_name]
```
就能產生名為`game_name`的資料夾在games中，裡面已經有初始版本的`config.json`, `client.py`, `server.py`供給使用者去開發

##  特色功能 (加分項)

### 1. Plugin 系統
* 位於 `player/plugins/`，支援動態載入。
* **功能展示**:
    * **Music Plugin**: 進入房間自動播放背景音樂 (需 `bgm.mp3`)。
    * **Theme Plugin**: 切換 UI 風格 (暗黑模式/可愛模式)。
* **操作**: 在主選單 `4. 擴充功能` 中可自由安裝/移除/啟用/停用。

### 2. 遊戲實作
* **Draw Guess (你畫我猜)**: 完整 GUI、即時繪圖同步、聊天室猜題、斷線自動判定勝利。
* **Tetris (俄羅斯方塊)**: 雙人對戰，支援即時觀看對手畫面。

### 3. UX 優化
* **下載隔離**: 不同玩家帳號擁有獨立下載目錄。
* **版本控管**: 自動偵測 Server 版本與本地版本，提示更新。
* **防呆機制**: 房間人數不足無法開局、重複登入阻擋。