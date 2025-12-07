# server.py
import time
import sys

print("Demo Game Server is running...")
sys.stdout.flush()

# 保持程式執行，模擬伺服器運作，直到被系統關閉
try:
    while True:
        time.sleep(10)
except KeyboardInterrupt:
    pass