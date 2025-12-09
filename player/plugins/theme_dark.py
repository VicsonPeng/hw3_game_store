DESCRIPTION = "酷炫暗黑主題"

# 定義配色方案
THEME_DATA = {
    "main_bg": "#2b2b2b",       # 主背景 (深灰)
    "nav_bg": "#1a1a1a",        # 導覽列 (更深灰)
    "nav_fg": "#00ff00",        # 導覽文字 (駭客綠)
    "header_bg": "#000000",     # 頂部標題 (全黑)
    "header_fg": "#00ff00",     # 標題文字 (駭客綠)
    "content_bg": "#2b2b2b",    # 內容區背景
    "text_fg": "#ffffff",       # 一般文字 (白)
    
    "btn_bg": "#444444",        # 按鈕背景
    "btn_fg": "#ffffff",        # 按鈕文字
    "btn_primary": "#006400",   # 主要按鈕 (深綠)
    "btn_danger": "#8b0000",    # 危險按鈕 (深紅)
    
    "entry_bg": "#555555",      # 輸入框背景
    "entry_fg": "#ffffff",      # 輸入框文字
    
    "list_bg": "#333333",       # 列表背景
    "list_fg": "#ffffff",       # 列表文字
    "list_select": "#555555",   # 列表選取色
    
    "font_family": "Consolas"   # 字體
}

def get_theme():
    return THEME_DATA