import tkinter as tk
import ttkbootstrap as ttk
from ttkbootstrap.constants import *
import subprocess
import socket
import time
import threading
import os
import sys

SERVER_SCRIPT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "flask_admin", "app.py")
PORT = 3000

def get_lan_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except:
        return "127.0.0.1"

class ServerManager:
    def __init__(self, root):
        self.root = root
        self.root.title("库存服务管理器")
        self.root.geometry("520x420")
        self.root.resizable(False, False)
        
        self.process = None
        self.running = False
        self.lan_ip = get_lan_ip()
        
        main = ttk.Frame(root, padding=20)
        main.pack(fill=BOTH, expand=YES)
        
        # 标题
        ttk.Label(main, text="菜鸟库存查询服务 开关面板", font=("Microsoft YaHei", 14, "bold")).pack(pady=(0, 5))
        ttk.Label(main, text=f"端口: {PORT}  |  本机 IP: {self.lan_ip}", foreground="gray").pack(pady=(0, 15))
        
        # 状态指示
        status_frame = ttk.Frame(main)
        status_frame.pack(fill=X, pady=5)
        self.status_dot = tk.Canvas(status_frame, width=16, height=16, highlightthickness=0)
        self.status_dot.pack(side=LEFT, padx=(0, 10))
        self.dot = self.status_dot.create_oval(2, 2, 14, 14, fill="gray")
        self.status_label = ttk.Label(status_frame, text="未启动", font=("Microsoft YaHei", 11, "bold"))
        self.status_label.pack(side=LEFT)
        
        # 访问链接
        self.url_label = ttk.Label(main, text="", font=("Consolas", 10), foreground="#409eff", cursor="hand2")
        self.url_label.pack(pady=(5, 15))
        
        # 按钮
        btn_frame = ttk.Frame(main)
        btn_frame.pack(fill=X, pady=5)
        self.start_btn = ttk.Button(btn_frame, text="启动服务", command=self.start_server, bootstyle=SUCCESS, width=12)
        self.start_btn.pack(side=LEFT, padx=(0, 15))
        self.stop_btn = ttk.Button(btn_frame, text="停止服务", command=self.stop_server, bootstyle=DANGER, width=12, state=DISABLED)
        self.stop_btn.pack(side=LEFT)
        
        # 日志
        log_frame = ttk.Labelframe(main, text=" 服务日志 ", padding=8)
        log_frame.pack(fill=BOTH, expand=YES, pady=10)
        self.log_text = tk.Text(log_frame, height=8, font=("Consolas", 10), bg="black", fg="#00ff00", insertbackground="white", relief=tk.FLAT)
        self.log_text.pack(side=LEFT, fill=BOTH, expand=YES)
        scrollbar = ttk.Scrollbar(log_frame, command=self.log_text.yview)
        scrollbar.pack(side=RIGHT, fill=Y)
        self.log_text.config(yscrollcommand=scrollbar.set)
        
        self.log("服务管理器已就绪")
        self.log(f"访问地址: http://{self.lan_ip}:{PORT}")
        
        # 关闭窗口时自动停服务
        root.protocol("WM_DELETE_WINDOW", self.on_close)

    def log(self, msg):
        t = time.strftime("%H:%M:%S")
        self.log_text.insert(END, f"[{t}] {msg}\n")
        self.log_text.see(END)

    def set_status(self, running):
        self.running = running
        if running:
            self.status_dot.itemconfig(self.dot, fill="#00ff00")
            self.status_label.config(text="运行中")
            self.url_label.config(text=f"http://{self.lan_ip}:{PORT}")
            self.start_btn.config(state=DISABLED)
            self.stop_btn.config(state=NORMAL)
        else:
            self.status_dot.itemconfig(self.dot, fill="gray")
            self.status_label.config(text="未启动")
            self.url_label.config(text="")
            self.start_btn.config(state=NORMAL)
            self.stop_btn.config(state=DISABLED)

    def start_server(self):
        if self.running:
            return
        self.log("正在启动 Flask 服务...")
        try:
            self.process = subprocess.Popen(
                [sys.executable, SERVER_SCRIPT],
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, encoding="utf-8", errors="replace",
                creationflags=subprocess.CREATE_NO_WINDOW
            )
            self.set_status(True)
            self.log("Flask 服务已启动")
            
            # 后台读取输出
            threading.Thread(target=self.read_output, daemon=True).start()
        except Exception as e:
            self.log(f"启动失败: {e}")

    def stop_server(self):
        if self.process:
            self.log("正在停止服务...")
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
            self.process = None
        self.set_status(False)
        self.log("服务已停止")

    def read_output(self):
        if self.process and self.process.stdout:
            for line in self.process.stdout:
                line = line.strip()
                if line:
                    self.root.after(0, self.log, line)

    def on_close(self):
        self.stop_server()
        self.root.destroy()

if __name__ == "__main__":
    root = ttk.Window(themename="darkly")
    app = ServerManager(root)
    root.mainloop()
