@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo ============================================
echo   利润核算 Web 服务 - 依赖安装
echo ============================================

if exist venv\Scripts\python.exe (
    echo [1/3] 使用已有虚拟环境 venv
) else (
    echo [1/3] 创建虚拟环境 venv
    py -3 -m venv venv
    if errorlevel 1 (
        echo 创建虚拟环境失败，请确认已安装 Python 3 并勾选 Add to PATH
        pause
        exit /b 1
    )
)

echo [2/3] 升级 pip
venv\Scripts\python.exe -m pip install --upgrade pip

echo [3/3] 安装依赖
venv\Scripts\python.exe -m pip install -r requirements.txt
if errorlevel 1 (
    echo 依赖安装失败，请检查网络后重新运行
    pause
    exit /b 1
)

echo.
echo 安装完成！双击 start.bat 启动服务。
pause
