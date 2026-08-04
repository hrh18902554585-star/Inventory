import os
import glob
import tkinter as tk
from tkinter import filedialog, messagebox
import ttkbootstrap as ttk
from ttkbootstrap.constants import *
import threading
from PIL import Image, ImageFile
import datetime

# 允许加载截断的图片
ImageFile.LOAD_TRUNCATED_IMAGES = True

class ImageRenamerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("图片批量清洗与重命名工具 v2.1")
        self.root.geometry("700x750")
        
        # 变量
        self.folder_paths = []
        self.status_var = ttk.StringVar(value="准备就绪")
        self.progress_var = ttk.DoubleVar()
        
        # 支持的图片格式
        self.supported_exts = ('.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp', '.tiff')
        
        self.create_widgets()
        self.log("程序启动成功，准备就绪。")
        
    def create_widgets(self):
        # 主框架 padding
        main_frame = ttk.Frame(self.root, padding=20)
        main_frame.pack(fill=BOTH, expand=YES)
        
        # 标题区域
        title_label = ttk.Label(main_frame, text="图片批量清洗与重命名", font=("Helvetica", 18, "bold"), bootstyle=PRIMARY)
        title_label.pack(pady=(0, 10))
        
        # 文件夹选择区域
        folder_frame = ttk.Labelframe(main_frame, text=" 选择包含图片的文件夹 (支持多选文件夹) ", padding=15, bootstyle=INFO)
        folder_frame.pack(fill=X, pady=5)
        
        btn_frame = ttk.Frame(folder_frame)
        btn_frame.pack(fill=X, pady=(0, 5))
        
        ttk.Button(btn_frame, text="➕ 添加文件夹", command=self.add_folder, bootstyle=PRIMARY).pack(side=LEFT, padx=(0, 10))
        ttk.Button(btn_frame, text="🗑 清空列表", command=self.clear_folders, bootstyle=SECONDARY).pack(side=LEFT)
        
        self.folder_listbox = tk.Listbox(folder_frame, height=4, font=("Helvetica", 10))
        self.folder_listbox.pack(fill=X, expand=YES)
        
        # 按钮区域
        action_frame = ttk.Frame(main_frame, padding=(0, 5))
        action_frame.pack(fill=X, pady=5)
        self.start_btn = ttk.Button(action_frame, text="🚀 一键清洗并重命名", command=self.start_rename_thread, bootstyle=SUCCESS, padding=10)
        self.start_btn.pack(fill=X)
        
        # 进度区域
        progress_frame = ttk.Labelframe(main_frame, text=" 处理进度 ", padding=15)
        progress_frame.pack(fill=X, pady=5)
        self.progress_bar = ttk.Progressbar(progress_frame, variable=self.progress_var, maximum=100, bootstyle=SUCCESS)
        self.progress_bar.pack(fill=X, pady=(0, 10))
        ttk.Label(progress_frame, textvariable=self.status_var, font=("Helvetica", 10, "bold"), bootstyle=PRIMARY).pack(anchor=W)

        # 日志区域
        log_frame = ttk.Labelframe(main_frame, text=" 运行日志 (实时) ", padding=10)
        log_frame.pack(fill=BOTH, expand=YES, pady=5)
        self.log_text = tk.Text(log_frame, height=8, font=("Consolas", 9), bg="#f8f9fa", relief=tk.FLAT)
        self.log_text.pack(side=LEFT, fill=BOTH, expand=YES)
        scrollbar = ttk.Scrollbar(log_frame, command=self.log_text.yview)
        scrollbar.pack(side=RIGHT, fill=Y)
        self.log_text.config(yscrollcommand=scrollbar.set)

    def log(self, message):
        # 1. 尝试写入本地文件，防止软件直接崩溃/卡死时没有痕迹
        try:
            with open("rename_tool_debug.log", "a", encoding="utf-8") as f:
                now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                f.write(f"[{now}] {message}\n")
        except:
            pass
            
        # 2. 更新UI，必须使用 after 跨线程安全更新
        self.root.after(0, self._log_ui, message)

    def _log_ui(self, message):
        now = datetime.datetime.now().strftime("%H:%M:%S")
        self.log_text.insert(tk.END, f"[{now}] {message}\n")
        self.log_text.see(tk.END)

    def add_folder(self):
        folder = filedialog.askdirectory()
        if folder and folder not in self.folder_paths:
            self.folder_paths.append(folder)
            self.folder_listbox.insert(tk.END, folder)
            self.log(f"添加文件夹: {folder}")

    def clear_folders(self):
        self.folder_paths.clear()
        self.folder_listbox.delete(0, tk.END)
        self.log("已清空文件夹列表")

    def start_rename_thread(self):
        if not self.folder_paths:
            messagebox.showwarning("警告", "请先添加至少一个文件夹！")
            return
            
        self.start_btn.config(state=DISABLED, text="正在处理中...")
        self.progress_var.set(0)
        self.status_var.set("正在扫描图片...")
        self.log("=== 开始执行批量清洗与重命名 ===")
        
        folders = list(self.folder_paths)
        threading.Thread(target=self.process_rename, args=(folders,), daemon=True).start()

    def process_rename(self, folders):
        try:
            total_processed = 0
            total_folders = len(folders)
            
            for f_idx, folder in enumerate(folders):
                self.log(f"开始扫描文件夹 ({f_idx+1}/{total_folders}): {folder}")
                # 获取所有图片文件
                image_files = []
                for file in os.listdir(folder):
                    file_path = os.path.join(folder, file)
                    if os.path.isfile(file_path):
                        ext = os.path.splitext(file)[1].lower()
                        if ext in self.supported_exts:
                            image_files.append(file_path)
                
                if not image_files:
                    self.log(f"文件夹为空或无支持的图片: {folder}")
                    continue
                    
                # 按文件的修改时间排序（从旧到新）
                image_files.sort(key=os.path.getmtime)
                self.log(f"找到 {len(image_files)} 张图片，开始清洗...")
                
                # 第一步：重新输出（清洗标记）并重命名为临时后缀
                temp_files = []
                for i, old_path in enumerate(image_files):
                    dir_name = os.path.dirname(old_path)
                    ext = os.path.splitext(old_path)[1].lower()
                    
                    # 避免在原目录直接使用相同的扩展名产生覆盖风险，使用完全独立的后缀
                    temp_name = f"__temp_clean_{i}__.tmp"
                    temp_path = os.path.join(dir_name, temp_name)
                    
                    try:
                        if i % 50 == 0:
                            self.log(f"正在清洗进度: {i+1}/{len(image_files)}")

                        # 核心：使用 Pillow 重新读取并保存，这会丢弃所有末尾追加的隐藏文本和部分 EXIF 标记
                        with Image.open(old_path) as img:
                            img.info.clear() # 清空元数据字典
                            
                            # 处理 RGBA 存为 JPG 的报错
                            if ext in ['.jpg', '.jpeg'] and img.mode in ('RGBA', 'P'):
                                img = img.convert('RGB')
                                
                            # 重新编码保存到临时文件
                            if ext in ['.jpg', '.jpeg', '.webp']:
                                img.save(temp_path, format=Image.registered_extensions().get(ext, 'JPEG'), quality=95)
                            else:
                                # 对于没有明确质量参数的格式
                                img.save(temp_path, format=Image.registered_extensions().get(ext, 'PNG'))
                                
                        # 只有在成功写入临时文件后，才删除原文件
                        if os.path.exists(temp_path) and os.path.getsize(temp_path) > 0:
                            os.remove(old_path)
                            temp_files.append((temp_path, ext))
                        else:
                            raise Exception("生成的临时文件为空")
                            
                    except Exception as e:
                        self.log(f"[警告] 图片清洗失败，将使用普通重命名: {old_path} - {e}")
                        # 失败回退到普通的重命名（针对损坏但仍可显示的图片）
                        # 确保如果有残留的空临时文件，先删除
                        if os.path.exists(temp_path):
                            try: os.remove(temp_path)
                            except: pass
                            
                        try:
                            os.rename(old_path, temp_path)
                            temp_files.append((temp_path, ext))
                        except Exception as re_e:
                            self.log(f"[错误] 无法重命名原文件: {old_path} - {re_e}")
                        
                    # 限制 UI 更新频率，避免卡死 Tkinter 主线程
                    if i % 10 == 0 or i == len(image_files) - 1:
                        progress = ((f_idx + (i + 1) / len(image_files) * 0.5) / total_folders) * 100
                        self.root.after(0, self.update_progress, progress, f"文件夹 {f_idx+1}/{total_folders} - 正在清洗: {i+1}/{len(image_files)}")
                    
                self.log(f"开始重命名文件夹 {f_idx+1}/{total_folders} 的图片...")

                # 第二步：正式重命名为 1, 2, 3...
                for i, (temp_path, ext) in enumerate(temp_files):
                    dir_name = os.path.dirname(temp_path)
                    new_name = f"{i + 1}{ext}"
                    new_path = os.path.join(dir_name, new_name)
                    
                    # 防止冲突，如果目标已存在先删除
                    if os.path.exists(new_path) and new_path != temp_path:
                        try:
                            os.remove(new_path)
                        except Exception as e:
                            self.log(f"[警告] 无法删除已存在的文件 {new_path}: {e}")
                        
                    try:
                        os.rename(temp_path, new_path)
                        total_processed += 1
                    except Exception as e:
                        self.log(f"[错误] 重命名 {temp_path} 到 {new_path} 失败: {e}")
                    
                    # 限制 UI 更新频率
                    if i % 10 == 0 or i == len(temp_files) - 1:
                        progress = ((f_idx + 0.5 + (i + 1) / len(temp_files) * 0.5) / total_folders) * 100
                        self.root.after(0, self.update_progress, progress, f"文件夹 {f_idx+1}/{total_folders} - 正在重命名: {i+1}/{len(temp_files)}")
                
            self.log("=== 所有处理完成 ===")
            self.root.after(0, lambda: self.finish_processing(f"处理完成！成功清洗并重命名了 {total_processed} 张图片。"))
            
        except Exception as e:
            self.log(f"严重错误: {str(e)}")
            self.root.after(0, lambda: self.finish_processing(f"发生错误: {str(e)}", is_error=True))

    def update_progress(self, val, text):
        self.progress_var.set(val)
        self.status_var.set(text)

    def finish_processing(self, msg, is_error=False):
        self.status_var.set(msg)
        self.start_btn.config(state=NORMAL, text="🚀 一键清洗并重命名")
        if is_error:
            messagebox.showerror("错误", msg)
        else:
            messagebox.showinfo("成功", msg)

if __name__ == "__main__":
    root = ttk.Window(themename="cosmo")
    app = ImageRenamerApp(root)
    root.mainloop()