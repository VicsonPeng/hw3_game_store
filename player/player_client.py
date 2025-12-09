import tkinter as tk
from tkinter import ttk, messagebox, simpledialog
import socket
import sys
import os
import json
import zipfile
import subprocess
import threading
import importlib.util
import argparse
import shutil

# 確保能 import common
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from common.utils import send_json, recv_json, recv_file

# --- 全域設定 ---
HOST = '127.0.0.1'
PORT = 5555
# 這些路徑依賴使用者，先設預設值或 None
DOWNLOAD_DIR = 'player/downloads' 
GLOBAL_PLUGINS_DIR = 'player/plugins' # 插件來源 (商店)
USER_PLUGINS_DIR = None               # 玩家插件目錄
PLUGIN_CONFIG_FILE = None             # 玩家設定檔

client_lock = threading.Lock()

# === [新增] 主題系統 ===
DEFAULT_THEME = {
    "main_bg": "#f0f0f0",
    "nav_bg": "#333333",
    "nav_fg": "white",
    "header_bg": "#333333",
    "header_fg": "white",
    "content_bg": "#f0f0f0",
    "text_fg": "black",
    "btn_bg": "#e0e0e0",
    "btn_fg": "black",
    "btn_primary": "#4CAF50",
    "btn_danger": "#d9534f",
    "entry_bg": "white",
    "entry_fg": "black",
    "list_bg": "white",
    "list_fg": "black",
    "list_select": "#0078d7",
    "font_family": "Arial"
}
CURRENT_THEME = DEFAULT_THEME.copy()

# === Helper Functions ===

def safe_request(client, req_data):
    try:
        with client_lock:
            if send_json(client, req_data):
                return recv_json(client)
    except Exception as e:
        print(f"Network Error: {e}")
    return None

def get_local_version(game_name):
    try:
        paths_to_check = [
            os.path.join(DOWNLOAD_DIR, game_name, 'config.json'),
            os.path.join(DOWNLOAD_DIR, game_name, game_name, 'config.json')
        ]
        for p in paths_to_check:
            if os.path.exists(p):
                with open(p, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    return data.get('version', '0.0')
    except: pass
    return None

def launch_game_client(game_name, username, game_host, game_port, token):
    try:
        game_root = os.path.join(DOWNLOAD_DIR, game_name)
        if not os.path.exists(game_root): return False, "尚未下載", None
        
        target = game_root
        nested = os.path.join(game_root, game_name)
        if os.path.exists(nested) and os.path.exists(os.path.join(nested, 'config.json')):
            target = nested
        
        cfg_path = os.path.join(target, 'config.json')
        if not os.path.exists(cfg_path): return False, "config.json 遺失", None

        with open(cfg_path, 'r', encoding='utf-8') as f: config = json.load(f)
        script = config['client']['script']
        args = config['client']['args_template'].format(
            host=game_host, port=game_port, user=username, token=token
        )
        cmd = [sys.executable, script] + args.split()
        proc = subprocess.Popen(cmd, cwd=target)
        return True, "啟動成功", proc
    except Exception as e:
        return False, str(e), None

def download_game_task(client, game_name):
    try:
        with client_lock:
            if not send_json(client, {'command': 'DOWNLOAD_GAME_INIT', 'payload': {'game_name': game_name}}):
                return False, "發送請求失敗"
            resp = recv_json(client)
            if not resp or resp.get('status') != 'ready_to_send':
                return False, resp.get('message', 'Server error')
            file_info = recv_json(client)
            filesize = file_info['size']
            save_path = os.path.join(DOWNLOAD_DIR, f"{game_name}.zip")
            os.makedirs(DOWNLOAD_DIR, exist_ok=True)
            if not recv_file(client, save_path, filesize):
                return False, "傳輸中斷"
        try:
            with zipfile.ZipFile(save_path, 'r') as zip_ref:
                extract_path = os.path.join(DOWNLOAD_DIR, game_name)
                zip_ref.extractall(extract_path)
            os.remove(save_path)
            return True, "安裝完成"
        except Exception as e: return False, f"解壓失敗: {e}"
    except Exception as e: return False, str(e)

# === Plugin System (User Isolated) ===

def load_plugin_config():
    if PLUGIN_CONFIG_FILE and os.path.exists(PLUGIN_CONFIG_FILE):
        try:
            with open(PLUGIN_CONFIG_FILE, 'r', encoding='utf-8') as f: return json.load(f)
        except: pass
    return {}

def save_plugin_config(config):
    if PLUGIN_CONFIG_FILE:
        try:
            with open(PLUGIN_CONFIG_FILE, 'w', encoding='utf-8') as f: json.dump(config, f, indent=4)
        except: pass

def _load_user_plugin(filename):
    """從玩家目錄載入插件"""
    if not USER_PLUGINS_DIR: return None
    path = os.path.join(USER_PLUGINS_DIR, filename)
    if not os.path.exists(path): return None
    
    cfg = load_plugin_config()
    if not cfg.get(filename, True): return None # 預設啟用，若 config 寫 False 則不載入

    try:
        spec = importlib.util.spec_from_file_location(filename[:-3], path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod
    except Exception as e:
        print(f"[Plugin] Load failed: {e}")
    return None

def load_music_plugin():
    return _load_user_plugin('music_plugin.py')

def load_theme():
    global CURRENT_THEME
    CURRENT_THEME = DEFAULT_THEME.copy()
    
    mod_dark = _load_user_plugin('theme_dark.py')
    if mod_dark: 
        try: CURRENT_THEME.update(mod_dark.get_theme())
        except: pass
        
    mod_cute = _load_user_plugin('theme_cute.py')
    if mod_cute:
        try: CURRENT_THEME.update(mod_cute.get_theme())
        except: pass

# ============================
#        GUI Frames
# ============================

class LoginFrame(tk.Frame):
    def __init__(self, master, on_login_success):
        super().__init__(master)
        self.configure(bg=CURRENT_THEME['main_bg'])
        self.on_login_success = on_login_success
        self.pack(expand=True, fill='both')

        frame = tk.Frame(self, padx=20, pady=20, bg=CURRENT_THEME['content_bg'])
        frame.place(relx=0.5, rely=0.5, anchor='center')

        tk.Label(frame, text="Game Store System", font=(CURRENT_THEME['font_family'], 20, "bold"), 
                 bg=CURRENT_THEME['content_bg'], fg=CURRENT_THEME['text_fg']).pack(pady=20)

        tk.Label(frame, text="Username:", bg=CURRENT_THEME['content_bg'], fg=CURRENT_THEME['text_fg']).pack(anchor='w')
        self.entry_user = tk.Entry(frame, bg=CURRENT_THEME['entry_bg'], fg=CURRENT_THEME['entry_fg'])
        self.entry_user.pack(fill='x', pady=5)

        tk.Label(frame, text="Password:", bg=CURRENT_THEME['content_bg'], fg=CURRENT_THEME['text_fg']).pack(anchor='w')
        self.entry_pwd = tk.Entry(frame, show="*", bg=CURRENT_THEME['entry_bg'], fg=CURRENT_THEME['entry_fg'])
        self.entry_pwd.pack(fill='x', pady=5)

        tk.Button(frame, text="Login / Register", command=self.do_login, 
                  bg=CURRENT_THEME['btn_primary'], fg="white").pack(fill='x', pady=20)

    def do_login(self):
        u = self.entry_user.get().strip()
        p = self.entry_pwd.get().strip()
        if not u or not p:
            messagebox.showerror("Error", "請輸入帳號密碼")
            return

        resp = safe_request(self.master.client, {
            'command': 'LOGIN', 
            'payload': {'username': u, 'password': p, 'role': 'player'}
        })

        if resp and resp['status'] == 'success':
            self.on_login_success(u)
        else:
            msg = resp.get('message', 'Unknown Error') if resp else "Connection Failed"
            messagebox.showerror("Login Failed", msg)


class MainDashboard(tk.Frame):
    def __init__(self, master, username):
        super().__init__(master)
        self.configure(bg=CURRENT_THEME['main_bg'])
        self.username = username
        self.client = master.client
        self.pack(expand=True, fill='both')
        
        # 導覽列
        self.nav_frame = tk.Frame(self, width=150, bg=CURRENT_THEME['nav_bg'])
        self.nav_frame.pack(side='left', fill='y')
        self.nav_frame.pack_propagate(False)

        # 內容區
        self.content_frame = tk.Frame(self, bg=CURRENT_THEME['content_bg'])
        self.content_frame.pack(side='right', expand=True, fill='both')

        # 導覽按鈕
        self.create_nav_btn("🛒 商城", self.show_store)
        self.create_nav_btn("📂 收藏庫", self.show_library)
        self.create_nav_btn("👥 活躍房間", self.show_room_list)
        self.create_nav_btn("🌐 線上玩家", self.show_online)
        self.create_nav_btn("🔌 擴充功能", self.show_plugins)
        
        tk.Button(self.nav_frame, text="登出", command=master.logout, 
                  bg=CURRENT_THEME['btn_danger'], fg="white").pack(side='bottom', fill='x', padx=5, pady=10)

        self.current_page = None
        self.show_store()

    def create_nav_btn(self, text, command):
        btn = tk.Button(self.nav_frame, text=text, command=command, relief='flat', pady=10, 
                        bg=CURRENT_THEME['nav_bg'], fg=CURRENT_THEME['nav_fg'], 
                        activebackground=CURRENT_THEME['header_bg'], activeforeground=CURRENT_THEME['header_fg'],
                        font=(CURRENT_THEME['font_family'], 10))
        btn.pack(fill='x')

    def switch_page(self, page_class, *args):
        if self.current_page:
            self.current_page.destroy()
        self.current_page = page_class(self.content_frame, self.client, self.username, self) 
        self.current_page.pack(expand=True, fill='both', padx=20, pady=20)

    def show_store(self): self.switch_page(StorePage)
    def show_library(self): self.switch_page(LibraryPage)
    def show_room_list(self): self.switch_page(RoomListPage)
    def show_online(self): self.switch_page(OnlinePage)
    def show_plugins(self): self.switch_page(PluginsPage)
    
    def open_room_lobby(self, room_id):
        if self.current_page: self.current_page.destroy()
        self.current_page = RoomLobbyPage(self.content_frame, self.client, self.username, room_id, self)
        self.current_page.pack(expand=True, fill='both')

class StorePage(tk.Frame):
    def __init__(self, master, client, username, dashboard):
        super().__init__(master)
        self.configure(bg=CURRENT_THEME['content_bg'])
        self.client = client
        self.username = username
        self.dashboard = dashboard
        
        tk.Label(self, text="遊戲商城", font=(CURRENT_THEME['font_family'], 18, "bold"), 
                 bg=CURRENT_THEME['content_bg'], fg=CURRENT_THEME['text_fg']).pack(anchor='w', pady=(0,10))
        
        cols = ("Name", "Type", "Rating", "MinPlayers", "Version", "Status")
        self.tree = ttk.Treeview(self, columns=cols, show='headings', height=15)
        for col in cols: self.tree.heading(col, text=col)
        self.tree.column("Name", width=150)
        self.tree.pack(expand=True, fill='both')
        self.tree.bind("<Double-1>", self.on_item_double_click)

        style = ttk.Style()
        style.configure("Treeview", background=CURRENT_THEME['list_bg'], 
                        foreground=CURRENT_THEME['list_fg'], fieldbackground=CURRENT_THEME['list_bg'])
        style.map('Treeview', background=[('selected', CURRENT_THEME['list_select'])])

        tk.Button(self, text="重新整理", command=self.load_data, bg=CURRENT_THEME['btn_bg'], fg=CURRENT_THEME['btn_fg']).pack(pady=10)
        self.load_data()

    def load_data(self):
        for item in self.tree.get_children(): self.tree.delete(item)
        resp = safe_request(self.client, {'command': 'LIST_GAMES'})
        if resp and resp['status'] == 'success':
            self.games_data = resp['games']
            for name, info in self.games_data.items():
                local_v = get_local_version(name)
                status = "未安裝"
                if local_v:
                    status = "已安裝" if local_v >= info['version'] else "可更新"
                
                self.tree.insert("", "end", values=(
                    name, 
                    info.get('game_type', 'GUI'),
                    f"⭐{info['rating']}",
                    f"{info.get('min_players', 1)}+",
                    info['version'],
                    status
                ))

    def on_item_double_click(self, event):
        item = self.tree.selection()
        if not item: return
        vals = self.tree.item(item, "values")
        game_name = vals[0]
        GameDetailWindow(self, self.client, game_name, self.games_data[game_name], self.username, self.dashboard)


class GameDetailWindow(tk.Toplevel):
    def __init__(self, parent, client, game_name, info, username, dashboard):
        super().__init__(parent)
        self.configure(bg=CURRENT_THEME['content_bg'])
        self.title(f"{game_name} - 詳細資訊")
        self.geometry("400x550")
        self.client = client
        self.game_name = game_name
        self.info = info
        self.username = username
        self.dashboard = dashboard

        tk.Label(self, text=game_name, font=(CURRENT_THEME['font_family'], 16, "bold"),
                 bg=CURRENT_THEME['content_bg'], fg=CURRENT_THEME['text_fg']).pack(pady=10)
        
        info_txt = (
            f"作者: {info['author']}\n"
            f"版本: {info['version']}\n"
            f"類型: {info.get('game_type', 'GUI')}\n"
            f"人數: {info.get('min_players', 1)}+\n\n"
            f"簡介: {info['description']}\n"
        )
        tk.Label(self, text=info_txt, justify='left', bg=CURRENT_THEME['content_bg'], fg=CURRENT_THEME['text_fg']).pack(pady=5, padx=20, anchor='w')

        btn_frame = tk.Frame(self, bg=CURRENT_THEME['content_bg'])
        btn_frame.pack(pady=10)

        local_v = get_local_version(game_name)
        dl_text = "下載遊戲"
        if local_v:
            dl_text = "更新遊戲" if local_v < info['version'] else "重新下載"
        
        tk.Button(btn_frame, text=dl_text, command=self.do_download, bg=CURRENT_THEME['btn_bg'], fg=CURRENT_THEME['btn_fg']).pack(fill='x', pady=2)
        if local_v:
            tk.Button(btn_frame, text="建立房間 (Play)", command=self.do_create_room, bg=CURRENT_THEME['btn_primary'], fg="white").pack(fill='x', pady=2)
        tk.Button(btn_frame, text="評分與留言", command=self.do_rate, bg=CURRENT_THEME['btn_bg'], fg=CURRENT_THEME['btn_fg']).pack(fill='x', pady=2)

        tk.Label(self, text="--- 最新評論 ---", bg=CURRENT_THEME['content_bg'], fg=CURRENT_THEME['text_fg']).pack(pady=(20, 5))
        self.review_box = tk.Text(self, height=8, width=40, state='disabled', bg=CURRENT_THEME['list_bg'], fg=CURRENT_THEME['list_fg'])
        self.review_box.pack(padx=10)
        self.load_reviews()

    def load_reviews(self):
        resp = safe_request(self.client, {'command': 'GET_GAME_DETAILS', 'payload': {'game_name': self.game_name}})
        if resp and resp['status'] == 'success':
            reviews = resp['game'].get('reviews', [])
            self.review_box.config(state='normal')
            self.review_box.delete(1.0, "end")
            if not reviews:
                self.review_box.insert("end", "(尚無評論)")
            for r in reviews[-5:]:
                self.review_box.insert("end", f"[{r['user']}] {r['score']}分: {r['comment']}\n")
            self.review_box.config(state='disabled')

    def do_download(self):
        self.config(cursor="wait")
        ok, msg = download_game_task(self.client, self.game_name)
        self.config(cursor="")
        messagebox.showinfo("下載結果", msg)
        if ok: self.destroy() 

    def do_create_room(self):
        if messagebox.askyesno("建立房間", f"確定要建立 {self.game_name} 的房間嗎？"):
            resp = safe_request(self.client, {'command': 'CREATE_ROOM', 'payload': {'game_name': self.game_name}})
            if resp and resp['status'] == 'success':
                self.destroy()
                self.dashboard.open_room_lobby(resp['room_id'])
            else:
                messagebox.showerror("錯誤", resp.get('message', '未知錯誤'))

    def do_rate(self):
        RateWindow(self, self.client, self.game_name)


class RateWindow(tk.Toplevel):
    def __init__(self, parent, client, game_name):
        super().__init__(parent)
        self.configure(bg=CURRENT_THEME['content_bg'])
        self.title("評分")
        self.client = client
        self.game_name = game_name

        tk.Label(self, text=f"評價 {game_name}", bg=CURRENT_THEME['content_bg'], fg=CURRENT_THEME['text_fg']).pack(pady=10)
        
        tk.Label(self, text="分數 (1-5):", bg=CURRENT_THEME['content_bg'], fg=CURRENT_THEME['text_fg']).pack()
        self.score_var = tk.StringVar(value="5")
        tk.Spinbox(self, from_=1, to=5, textvariable=self.score_var, width=5).pack()

        tk.Label(self, text="留言 (50字內):", bg=CURRENT_THEME['content_bg'], fg=CURRENT_THEME['text_fg']).pack()
        self.entry_comment = tk.Entry(self, width=30)
        self.entry_comment.pack(pady=5)

        tk.Button(self, text="送出", command=self.submit, bg=CURRENT_THEME['btn_primary'], fg="white").pack(pady=10)

    def submit(self):
        try:
            s = int(self.score_var.get())
            c = self.entry_comment.get().strip()
            if len(c) > 50:
                messagebox.showwarning("字數過長", "評論請限制在 50 字以內")
                return
            
            resp = safe_request(self.client, {'command': 'RATE_GAME', 'payload': {'game_name': self.game_name, 'score': s, 'comment': c}})
            if resp and resp['status'] == 'success':
                messagebox.showinfo("成功", "評價已送出！")
                self.destroy()
            else:
                msg = resp.get('message') if resp else "Connection error"
                if "play" in msg.lower(): # 未遊玩
                    messagebox.showerror("失敗", "您必須先遊玩過此遊戲才能評分！")
                else:
                    messagebox.showerror("失敗", msg)
        except ValueError: pass


class LibraryPage(tk.Frame):
    def __init__(self, master, client, username, dashboard):
        super().__init__(master)
        self.configure(bg=CURRENT_THEME['content_bg'])
        tk.Label(self, text="我的收藏庫 (已下載)", font=(CURRENT_THEME['font_family'], 18, "bold"), 
                 bg=CURRENT_THEME['content_bg'], fg=CURRENT_THEME['text_fg']).pack(anchor='w', pady=(0,10))
        
        self.listbox = tk.Listbox(self, font=(CURRENT_THEME['font_family'], 12), bg=CURRENT_THEME['list_bg'], fg=CURRENT_THEME['list_fg'])
        self.listbox.pack(expand=True, fill='both', pady=5)
        self.listbox.bind("<Double-1>", lambda e: self.do_create())
        
        tk.Button(self, text="建立房間", command=self.do_create, bg=CURRENT_THEME['btn_primary'], fg="white").pack(fill='x', pady=5)
        
        # 載入本地列表
        if os.path.exists(DOWNLOAD_DIR):
            for d in os.listdir(DOWNLOAD_DIR):
                if os.path.isdir(os.path.join(DOWNLOAD_DIR, d)):
                    v = get_local_version(d)
                    self.listbox.insert("end", f"{d} (v{v})")

        self.client = client
        self.dashboard = dashboard
        self.username = username

    def do_create(self):
        sel = self.listbox.curselection()
        if not sel: return
        txt = self.listbox.get(sel[0])
        game_name = txt.split(' ')[0] 
        resp = safe_request(self.client, {'command': 'CREATE_ROOM', 'payload': {'game_name': game_name}})
        if resp and resp['status'] == 'success':
            self.dashboard.open_room_lobby(resp['room_id'])
        else:
            messagebox.showerror("錯誤", resp.get('message', 'Failed'))


class RoomListPage(tk.Frame):
    def __init__(self, master, client, username, dashboard):
        super().__init__(master)
        self.configure(bg=CURRENT_THEME['content_bg'])
        self.client = client
        self.dashboard = dashboard
        
        tk.Label(self, text="活躍房間列表", font=(CURRENT_THEME['font_family'], 18, "bold"),
                 bg=CURRENT_THEME['content_bg'], fg=CURRENT_THEME['text_fg']).pack(anchor='w')
        
        cols = ("ID", "Game", "Host", "Status", "Players")
        self.tree = ttk.Treeview(self, columns=cols, show='headings', height=15)
        for c in cols: self.tree.heading(c, text=c)
        self.tree.column("ID", width=50)
        self.tree.pack(expand=True, fill='both', pady=10)
        self.tree.bind("<Double-1>", self.do_join)

        tk.Button(self, text="加入選定房間", command=self.do_join, bg=CURRENT_THEME['btn_bg'], fg=CURRENT_THEME['btn_fg']).pack(pady=5)
        tk.Button(self, text="重新整理", command=self.load_data, bg=CURRENT_THEME['btn_bg'], fg=CURRENT_THEME['btn_fg']).pack(pady=5)
        
        self.load_data()

    def load_data(self):
        for i in self.tree.get_children(): self.tree.delete(i)
        resp = safe_request(self.client, {'command': 'LIST_ROOMS'})
        if resp and resp['status'] == 'success':
            for rid, r in resp['rooms'].items():
                self.tree.insert("", "end", values=(
                    rid, r['game_name'], r['host'], r['status'], len(r['players'])
                ))

    def do_join(self, event=None):
        sel = self.tree.selection()
        if not sel: return
        val = self.tree.item(sel[0], "values")
        rid = val[0]
        gname = val[1]
        
        if not get_local_version(gname):
            if messagebox.askyesno("未安裝", f"尚未安裝 {gname}，是否前往下載？"):
                ok, msg = download_game_task(self.client, gname)
                if not ok: 
                    messagebox.showerror("下載失敗", msg)
                    return
            else: return

        resp = safe_request(self.client, {'command': 'JOIN_ROOM', 'payload': {'room_id': rid}})
        if resp and resp['status'] == 'success':
            self.dashboard.open_room_lobby(rid)
        else:
            messagebox.showerror("加入失敗", resp.get('message', 'Error'))


class RoomLobbyPage(tk.Frame):
    def __init__(self, master, client, username, room_id, dashboard):
        super().__init__(master)
        self.configure(bg=CURRENT_THEME['content_bg'])
        self.client = client
        self.username = username
        self.room_id = room_id
        self.dashboard = dashboard
        self.running = True
        self.in_game = False
        self.game_proc = None
        self.music_player = None
        self.game_name = ""

        mp = load_music_plugin()
        if mp:
            try:
                self.music_player = mp.create_music_player(room_id, username)
                self.music_player.start()
            except: pass

        top = tk.Frame(self, bg=CURRENT_THEME['content_bg'])
        top.pack(fill='x', pady=10)
        tk.Label(top, text=f"房間 {room_id} 大廳", font=(CURRENT_THEME['font_family'], 20, "bold"),
                 bg=CURRENT_THEME['content_bg'], fg=CURRENT_THEME['text_fg']).pack(side='left')
        
        self.lbl_info = tk.Label(self, text="載入中...", font=(CURRENT_THEME['font_family'], 12), 
                                 bg=CURRENT_THEME['entry_bg'], fg=CURRENT_THEME['text_fg'], padx=10, pady=10)
        self.lbl_info.pack(fill='x', padx=20)

        self.btn_start = tk.Button(self, text="開始遊戲 (Start)", command=self.do_start, 
                                   bg=CURRENT_THEME['btn_primary'], fg="white", state='disabled')
        self.btn_start.pack(pady=20, ipadx=20, ipady=10)
        
        tk.Button(self, text="離開房間 (Leave)", command=self.do_leave, 
                  bg=CURRENT_THEME['btn_danger'], fg="white").pack(pady=5)

        self.after(500, self.poll_room_info)

    def poll_room_info(self):
        if not self.running: return
        
        if self.in_game and self.game_proc:
            if self.game_proc.poll() is not None:
                self.on_game_end()
                return

        info = safe_request(self.client, {'command': 'GET_ROOM_INFO', 'payload': {'room_id': self.room_id}})
        if not info or info.get('status') != 'success':
            messagebox.showerror("連線中斷", "房間已關閉或連線中斷")
            self.do_leave(force=True)
            return

        self.game_name = info.get('game_name')
        host = info.get('host')
        players = info.get('players', [])
        status = info.get('room_status')
        
        txt = f"遊戲: {self.game_name}\n房主: {host}\n狀態: {status}\n\n玩家列表 ({len(players)}人):\n" + "\n".join([f"- {p}" for p in players])
        self.lbl_info.config(text=txt)

        if host == self.username:
            self.btn_start.config(state='normal')
        else:
            self.btn_start.config(state='disabled')

        if status == 'playing' and not self.in_game:
            self.start_game_client(info)

        self.after(1000, self.poll_room_info)

    def start_game_client(self, info):
        self.in_game = True
        if self.music_player: self.music_player.stop()
        
        # === [修正] 強制使用大廳連線的 IP (HOST) ===
        # 原本是: info['game_host']
        # 改成: HOST
        ok, msg, proc = launch_game_client(
            info['game_name'], 
            self.username, 
            HOST,  # <--- 這裡改成 HOST (即 140.113.17.11)
            info['game_port'], 
            info['token']
        )
        # ========================================
        
        if ok:
            self.game_proc = proc
        else:
            messagebox.showerror("啟動失敗", msg)
            self.in_game = False

    def on_game_end(self):
        self.in_game = False
        self.game_proc = None
        self.running = False 
        safe_request(self.client, {'command': 'LEAVE_ROOM', 'payload': {'room_id': self.room_id}})
        if self.music_player: self.music_player.stop()

        if messagebox.askyesno("遊戲結束", "要再來一局嗎？(重新開房)"):
             resp = safe_request(self.client, {'command': 'CREATE_ROOM', 'payload': {'game_name': self.game_name}})
             if resp and resp['status'] == 'success':
                 self.dashboard.open_room_lobby(resp['room_id'])
                 self.destroy()
                 return
        
        if messagebox.askyesno("評價", "是否要評論剛剛遊玩的遊戲？"):
             RateWindow(self.dashboard, self.client, self.game_name)

        self.dashboard.show_store()
        self.destroy()

    def do_start(self):
        # 1. 取得最新房間資訊以確認即時人數
        info = safe_request(self.client, {'command': 'GET_ROOM_INFO', 'payload': {'room_id': self.room_id}})
        if not info or info.get('status') != 'success':
            return 
            
        current_count = len(info.get('players', []))

        # 2. 讀取本地 Config 確認最小人數需求
        min_p = 1
        try:
            game_root = os.path.join(DOWNLOAD_DIR, self.game_name)
            target = game_root
            # 偵測內層目錄
            if os.path.exists(os.path.join(game_root, self.game_name, 'config.json')):
                target = os.path.join(game_root, self.game_name)
            
            cfg_path = os.path.join(target, 'config.json')
            if os.path.exists(cfg_path):
                with open(cfg_path, 'r', encoding='utf-8') as f:
                    min_p = json.load(f).get('min_players', 1)
        except Exception:
            pass

        # 3. [修正] 執行檢查：若人數不足則阻擋
        if current_count < min_p:
            messagebox.showwarning("人數不足", f"此遊戲 ({self.game_name}) 至少需要 {min_p} 人才能開始。\n目前人數: {current_count}")
            return 
        # ========================================

        # 4. 發送開始請求
        resp = safe_request(self.client, {'command': 'START_GAME', 'payload': {'room_id': self.room_id}})
        if resp and resp['status'] != 'success':
            messagebox.showwarning("無法開始", resp.get('message'))

    def do_leave(self, force=False):
        self.running = False
        if self.music_player: self.music_player.stop()
        if not force:
            safe_request(self.client, {'command': 'LEAVE_ROOM', 'payload': {'room_id': self.room_id}})
        self.dashboard.show_store()
        self.destroy()

class OnlinePage(tk.Frame):
    def __init__(self, master, client, username, dashboard):
        super().__init__(master)
        self.configure(bg=CURRENT_THEME['content_bg'])
        
        tk.Label(self, text="線上玩家列表", font=(CURRENT_THEME['font_family'], 18, "bold"), 
                 bg=CURRENT_THEME['content_bg'], fg=CURRENT_THEME['text_fg']).pack(pady=10)
        
        self.listbox = tk.Listbox(self, font=(CURRENT_THEME['font_family'], 12),
                                  bg=CURRENT_THEME['list_bg'], fg=CURRENT_THEME['list_fg'])
        self.listbox.pack(expand=True, fill='both', padx=20, pady=10)
        
        # 取得線上名單
        resp = safe_request(client, {'command': 'LIST_USERS'})
        if resp and resp.get('status') == 'success':
            for u in resp.get('users', []):
                self.listbox.insert("end", u)
        
        # 加入重新整理按鈕
        tk.Button(self, text="重新整理", command=self.refresh, 
                  bg=CURRENT_THEME['btn_bg'], fg=CURRENT_THEME['btn_fg']).pack(pady=5)

    def refresh(self):
        self.listbox.delete(0, "end")
        resp = safe_request(self.master.master.client, {'command': 'LIST_USERS'}) # 透過 master 取得 client
        # 或者更簡單，重新 reload page:
        # self.dashboard.show_online() 
        # 但這裡我們手動更新 listbox 體驗較好
        if resp and resp.get('status') == 'success':
            for u in resp.get('users', []):
                self.listbox.insert("end", u)

class PluginsPage(tk.Frame):
    def __init__(self, master, client, username, dashboard):
        super().__init__(master)
        self.configure(bg=CURRENT_THEME['content_bg'])
        self.dashboard = dashboard  # Store the dashboard instance
        
        tk.Label(self, text="擴充功能管理", font=(CURRENT_THEME['font_family'], 18),
                 bg=CURRENT_THEME['content_bg'], fg=CURRENT_THEME['text_fg']).pack(pady=10)
        
        # 確保 Global 目錄存在 (PluginsPage 需要讀取商店)
        if not os.path.exists(GLOBAL_PLUGINS_DIR): os.makedirs(GLOBAL_PLUGINS_DIR)
        
        # 載入 User Config
        self.cfg = load_plugin_config()

        # 列出 GLOBAL_PLUGINS_DIR 中的所有插件
        for f in os.listdir(GLOBAL_PLUGINS_DIR):
            if f.endswith('.py') and f != '__init__.py':
                # 檢查玩家目錄是否有安裝
                user_path = os.path.join(USER_PLUGINS_DIR, f) if USER_PLUGINS_DIR else None
                is_installed = os.path.exists(user_path) if user_path else False
                is_enabled = self.cfg.get(f, True)

                # 讀取描述
                desc = f
                try:
                    spec = importlib.util.spec_from_file_location("tmp", os.path.join(GLOBAL_PLUGINS_DIR, f))
                    mod = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(mod)
                    desc = getattr(mod, 'DESCRIPTION', f)
                except: pass

                frame = tk.Frame(self, bg=CURRENT_THEME['content_bg'])
                frame.pack(fill='x', padx=50, pady=5)
                
                # 狀態文字
                status_txt = "[未安裝]"
                if is_installed:
                    status_txt = "[已啟用]" if is_enabled else "[已停用]"
                
                tk.Label(frame, text=f"{f} ({status_txt}) - {desc}", 
                         bg=CURRENT_THEME['content_bg'], fg=CURRENT_THEME['text_fg']).pack(side='left')

                # 操作按鈕 (安裝/切換)
                if not is_installed:
                    tk.Button(frame, text="安裝", command=lambda fn=f: self.install(fn)).pack(side='right')
                else:
                    action = "停用" if is_enabled else "啟用"
                    tk.Button(frame, text=action, command=lambda fn=f, en=is_enabled: self.toggle(fn, en)).pack(side='right')

    def install(self, fname):
        src = os.path.join(GLOBAL_PLUGINS_DIR, fname)
        dst = os.path.join(USER_PLUGINS_DIR, fname)
        try:
            shutil.copy(src, dst)
            if "music" in fname: # 特例：複製素材
                mp3 = os.path.join(GLOBAL_PLUGINS_DIR, "bgm.mp3")
                if os.path.exists(mp3): shutil.copy(mp3, os.path.join(USER_PLUGINS_DIR, "bgm.mp3"))
            
            # 預設啟用
            self.cfg[fname] = True
            save_plugin_config(self.cfg)
            messagebox.showinfo("成功", f"{fname} 已安裝")
            
            # [Fix] Use self.dashboard instead of self.master to call show_plugins
            self.dashboard.show_plugins() 
            
        except Exception as e:
            messagebox.showerror("失敗", str(e))

    def toggle(self, fname, current_state):
        self.cfg[fname] = not current_state
        save_plugin_config(self.cfg)
        messagebox.showinfo("設定已變更", f"{fname} 已{'停用' if current_state else '啟用'} (需重啟生效)")
        
        # [Fix] Use self.dashboard instead of self.master to call show_plugins
        self.dashboard.show_plugins()


# ============================
#        App Entry
# ============================

class GameStoreApp(tk.Tk):
    def __init__(self, args):
        super().__init__()
        self.title("Game Store System (Player)")
        self.geometry("900x600")
        self.configure(bg=DEFAULT_THEME['main_bg'])
        
        global HOST, PORT
        HOST = args.host
        PORT = args.port
        
        self.client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            self.client.connect((HOST, PORT))
        except:
            messagebox.showerror("Error", f"無法連線至 {HOST}:{PORT}")
            self.destroy()
            return

        self.show_login()

    def show_login(self):
        LoginFrame(self, self.on_login_success)

    def on_login_success(self, username):
        # 設定路徑
        global DOWNLOAD_DIR, USER_PLUGINS_DIR, PLUGIN_CONFIG_FILE
        DOWNLOAD_DIR = os.path.join('player', 'downloads', username)
        USER_PLUGINS_DIR = os.path.join(DOWNLOAD_DIR, 'plugins')
        PLUGIN_CONFIG_FILE = os.path.join(USER_PLUGINS_DIR, 'plugin_config.json')

        if not os.path.exists(DOWNLOAD_DIR): os.makedirs(DOWNLOAD_DIR)
        if not os.path.exists(USER_PLUGINS_DIR): os.makedirs(USER_PLUGINS_DIR)
        
        # 載入主題
        load_theme() 
        if CURRENT_THEME != DEFAULT_THEME:
            self.configure(bg=CURRENT_THEME['main_bg'])
        
        for widget in self.winfo_children(): widget.destroy()
        MainDashboard(self, username)
    
    def logout(self):
        safe_request(self.client, {'command': 'LOGOUT'})
        for widget in self.winfo_children(): widget.destroy()
        self.show_login()

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('--host', type=str, required=True)
    parser.add_argument('--port', type=int, default=5555)
    args = parser.parse_args()
    
    app = GameStoreApp(args)
    app.mainloop()