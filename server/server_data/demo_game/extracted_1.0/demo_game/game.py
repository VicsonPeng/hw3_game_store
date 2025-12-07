import time

print("=== 這是 Demo Game 畫面 ===")
print("正在模擬連線至 Game Server...")
time.sleep(1)
print("遊戲開始！ (按 Ctrl+C 結束)")
try:
    while True:
        cmd = input("遊戲指令 > ")
        if cmd == 'exit':
            break
        print(f"你輸入了: {cmd}")
except KeyboardInterrupt:
    print("遊戲結束")