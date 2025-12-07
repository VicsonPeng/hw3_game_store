# client.py
import tkinter as tk

def main():
    root = tk.Tk()
    root.title("Demo Game Client")
    root.geometry("300x200")

    label = tk.Label(root, text="Demo Game\n啟動成功！", font=("Arial", 16))
    label.pack(expand=True)

    btn = tk.Button(root, text="關閉遊戲", command=root.destroy)
    btn.pack(pady=20)

    root.mainloop()

if __name__ == "__main__":
    main()