@echo off
chcp 65001 >nul
cd /d "%~dp0"

rem 如需更换端口，取消下一行注释并改成想要的端口
rem set PORT=8080

if not exist venv\Scripts\python.exe (
    echo 未找到虚拟环境，请先双击 install_deps.bat
    pause
    exit /b 1
)

echo 正在启动利润核算 Web 服务（服务运行期间请勿关闭本窗口）...
venv\Scripts\python.exe run.py
pause
