# -*- coding: utf-8 -*-
"""服务入口：初始化各模块并启动 HTTP 服务"""
import os
import sys
import socket
import ctypes

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PORT = int(os.environ.get("PORT", 5000))


def enable_ansi():
    """win10+ 控制台开启 ANSI 颜色支持，失败静默"""
    if os.name != "nt":
        return
    try:
        k32 = ctypes.windll.kernel32
        handle = k32.GetStdHandle(-11)
        mode = ctypes.c_uint32()
        if k32.GetConsoleMode(handle, ctypes.byref(mode)):
            k32.SetConsoleMode(handle, mode.value | 0x0004)
    except Exception:
        pass


def get_lan_ips():
    """逐个尝试获取局域网 IP（排除回环与链路本地）"""
    ips = []
    try:
        # 首选：UDP 连外部地址拿出口网卡 IP
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.connect(("8.8.8.8", 80))
            ips.append(s.getsockname()[0])
        finally:
            s.close()
    except Exception:
        pass
    try:
        # 兜底：遍历本机地址
        for _, _, _, _, addr in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ip = addr[0]
            if ip not in ips and not ip.startswith(("127.", "169.254.")):
                ips.append(ip)
    except Exception:
        pass
    return ips


def ensure_requirements():
    """requirements.txt 不存在则创建，确保关键依赖可安装"""
    path = os.path.join(BASE_DIR, "requirements.txt")
    if os.path.exists(path):
        return
    with open(path, "w", encoding="utf-8") as f:
        f.write("waitress\nflask\nopenpyxl\nrequests\n")


def main():
    enable_ansi()
    ensure_requirements()

    import logging_setup
    logging_setup.setup_logging()

    import db
    db.init_db()

    import tax_cache
    tax_cache.load_cache(os.path.join(BASE_DIR, "data", "tax_cache.json"))

    import task_manager
    task_manager.init_task_manager()
    task_manager.cleanup_outputs()

    from app import create_app
    from security import get_token

    app = create_app()
    token = get_token()

    RED = "\033[91m"
    YELLOW = "\033[93m"
    RESET = "\033[0m"

    print("=" * 56)
    print(f"  利润核算 Web 服务已启动")
    print(f"  本机访问:  http://127.0.0.1:{PORT}")
    for ip in get_lan_ips():
        print(f"  局域网访问: http://{ip}:{PORT}")
    print()
    print(f"  {RED}Token: {token}{RESET}")
    print(f"  {RED}浏览器首次访问时请在页面填写上方 Token{RESET}")
    print(f"  提示: 运行中请勿关闭此窗口")
    print("=" * 56)
    sys.stdout.flush()

    try:
        from waitress import serve
    except ImportError:
        print(f"{YELLOW}[警告] 未安装 waitress，已降级使用 Flask 内置服务器（生产建议: pip install waitress）{RESET}")
        app.run(host="0.0.0.0", port=PORT, threaded=True)
    else:
        serve(app, host="0.0.0.0", port=PORT, threads=8)


if __name__ == "__main__":
    main()
