import os
import tkinter as tk
from tkinter import filedialog, messagebox
import ttkbootstrap as ttk
from datetime import datetime
import threading
import time

class DirFileRenamerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("按目录层级重命名工具")
        self.root.geometry("650x500")
        
        self.folder_paths = []
        
        # UI 布局
        main_frame = ttk.Frame(self.root, padding=20)
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        title_lbl = ttk.Label(main_frame, text="层级归属批量重命名", font=("Helvetica", 16, "bold"))
        title_lbl.pack(pady=(0, 5))
        
        desc_lbl = ttk.Label(main_frame, text="规则: 取文件所在的上两级目录名 + 当前日期 + 序号\n例如: 低糖/趣味猴/图片.jpg -> 低糖趣味猴260730-1.jpg", foreground="gray")
        desc_lbl.pack(pady=(0, 15))
        
        btn_frame = ttk.Frame(main_frame)
        btn_frame.pack(fill=tk.X, pady=5)
        
        ttk.Button(btn_frame, text="1. 选择文件夹(可多次)", command=self.select_folders, bootstyle="primary").pack(side=tk.LEFT, padx=(0, 10))
        ttk.Button(btn_frame, text="清空已选", command=self.clear_folders, bootstyle="secondary").pack(side=tk.LEFT, padx=(0, 10))
        
        self.folder_label = ttk.Label(btn_frame, text="未选择任何文件夹", font=("Helvetica", 10))
        self.folder_label.pack(side=tk.LEFT)
        
        ttk.Button(main_frame, text="2. 🚀 开始重命名", command=self.start_rename, bootstyle="success").pack(fill=tk.X, pady=15)
        
        # 日志区域 (符合用户偏好的黑底绿字)
        log_frame = ttk.Labelframe(main_frame, text=" 实时日志面板 ", padding=10)
        log_frame.pack(fill=tk.BOTH, expand=True)
        
        self.log_text = tk.Text(log_frame, height=12, font=("Consolas", 10), bg="black", fg="#00ff00", insertbackground="white")
        self.log_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        scrollbar = ttk.Scrollbar(log_frame, command=self.log_text.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.log_text.config(yscrollcommand=scrollbar.set)

    def log(self, msg):
        self.root.after(0, self._log, msg)

    def _log(self, msg):
        t = time.strftime("%H:%M:%S")
        self.log_text.insert(tk.END, f"[{t}] {msg}\n")
        self.log_text.see(tk.END)

    def select_folders(self):
        folder = filedialog.askdirectory(title="选择需要处理的父文件夹")
        if folder:
            if folder not in self.folder_paths:
                self.folder_paths.append(folder)
            self.folder_label.config(text=f"已选择 {len(self.folder_paths)} 个文件夹")
            self.log(f"已加入处理队列: {folder}")

    def clear_folders(self):
        self.folder_paths.clear()
        self.folder_label.config(text="未选择任何文件夹")
        self.log("已清空选择的目录队列")

    def start_rename(self):
        if not self.folder_paths:
            messagebox.showwarning("提示", "请先选择需要处理的文件夹！")
            return
        self.log("启动重命名自动化流程...")
        threading.Thread(target=self.process_rename, daemon=True).start()

    def process_rename(self):
        date_str = datetime.now().strftime("%y%m%d")
        total_renamed = 0
        
        for root_folder in self.folder_paths:
            self.log(f"正在扫描目录树: {root_folder}")
            for dirpath, dirnames, filenames in os.walk(root_folder):
                # 过滤隐藏文件和系统文件
                files_to_rename = [f for f in filenames if not f.startswith('.')]
                if not files_to_rename:
                    continue
                    
                parent_name = os.path.basename(dirpath)
                grandparent_name = os.path.basename(os.path.dirname(dirpath))
                
                # 构建前缀
                if grandparent_name and not os.path.dirname(dirpath).endswith(':\\'):
                    prefix = f"{grandparent_name}{parent_name}"
                else:
                    prefix = f"{parent_name}"
                    
                self.log(f"-> 进入子目录 [{parent_name}], 命名模板: {prefix}{date_str}-X")
                
                seq = 1
                for filename in files_to_rename:
                    old_path = os.path.join(dirpath, filename)
                    ext = os.path.splitext(filename)[1]
                    
                    # 防止对已经符合命名规则的文件重复叠加后缀
                    if filename.startswith(f"{prefix}{date_str}-"):
                        self.log(f"   [跳过] {filename} (已符合规则)")
                        continue
                    
                    new_name = f"{prefix}{date_str}-{seq}{ext}"
                    new_path = os.path.join(dirpath, new_name)
                    
                    # 避免同名覆盖，自增序号
                    while os.path.exists(new_path) and old_path != new_path:
                        seq += 1
                        new_name = f"{prefix}{date_str}-{seq}{ext}"
                        new_path = os.path.join(dirpath, new_name)
                        
                    try:
                        os.rename(old_path, new_path)
                        self.log(f"   [成功] {filename} -> {new_name}")
                        total_renamed += 1
                        seq += 1
                    except Exception as e:
                        self.log(f"   [失败] {filename} 错误: {e}")
                        
        self.log(f"=== 流程结束！本次共成功重命名 {total_renamed} 个文件 ===")
        self.folder_paths.clear()
        self.root.after(0, lambda: self.folder_label.config(text="未选择任何文件夹"))

if __name__ == "__main__":
    # 采用深色主题，符合用户极客/控制台审美偏好
    root = ttk.Window(themename="darkly") 
    app = DirFileRenamerApp(root)
    root.mainloop()
