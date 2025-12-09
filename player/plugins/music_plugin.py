import threading
import time
import winsound
import sys

DESCRIPTION = "在進入房間時自動播放背景音樂"

class RoomMusicPlayer:
    def __init__(self, room_id, username):
        self.room_id = room_id
        self.running = False
        self.thread = None

    def start(self):
        if self.running: return
        self.running = True
        self.thread = threading.Thread(target=self._play_loop, daemon=True)
        self.thread.start()
        print(f"[Plugin] 🎵 背景音樂已啟動 (Room {self.room_id})")

    def stop(self):
        if not self.running: return
        self.running = False
        if self.thread:
            self.thread.join(timeout=1.0)
        print("[Plugin] 🎵 背景音樂已停止")

    def _play_loop(self):
        # 簡單的旋律 (頻率, 持續時間ms)
        melody = [
            (523, 300), (659, 300), (784, 300), (1046, 600),
            (784, 300), (1046, 900)
        ]
        
        while self.running:
            for freq, dur in melody:
                if not self.running: break
                try:
                    # Windows only
                    if sys.platform == "win32":
                        winsound.Beep(freq, dur)
                    else:
                        time.sleep(dur / 1000)
                except:
                    time.sleep(0.5)
                
                time.sleep(0.1)
            
            # 循環間隔
            time.sleep(2)

# Factory
def create_music_player(room_id, username):
    return RoomMusicPlayer(room_id, username)