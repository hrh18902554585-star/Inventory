import sys
import os

print(f"Python Executable: {sys.executable}")
print(f"Current Working Directory: {os.getcwd()}")

try:
    import requests
    print(f"Requests module found at: {requests.__file__}")
except ImportError:
    print("Requests module NOT found.")

import json

# 接口地址
url = "https://b.cainiao.com/merchantchargeorder/queryChargeOrderListNew"

# Cookie 变量 - 请在此处填入您的 Cookie
cookie_value = "YOUR_COOKIE_HERE"

# 设置请求头，模拟浏览器环境
headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Content-Type": "application/json",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Origin": "https://b.cainiao.com",
    "Referer": "https://b.cainiao.com/merchantchargeorder/list",
    "Cookie": cookie_value
}

# POST 请求参数
payload = {
    "orderNo": "YT8844569147030",
    "currentPage": 1,
    "pageSize": 10,
    "orderNoType": 0
}

def main():
    print(f"正在请求接口: {url}")
    print("请求参数:", json.dumps(payload, ensure_ascii=False))
    
    try:
        if 'requests' not in sys.modules:
             print("Please install requests module first.")
             return

        response = requests.post(url, headers=headers, json=payload)
        
        # 检查响应状态码
        if response.status_code == 200:
            print("请求成功！")
            try:
                # 尝试解析 JSON 响应
                result = response.json()
                print("响应结果:")
                print(json.dumps(result, indent=4, ensure_ascii=False))
            except json.JSONDecodeError:
                print("响应不是有效的 JSON 格式:")
                print(response.text)
        else:
            print(f"请求失败，状态码: {response.status_code}")
            print("响应内容:", response.text)
            
    except Exception as e:
        print(f"发生请求异常: {e}")

if __name__ == "__main__":
    if cookie_value == "YOUR_COOKIE_HERE":
        print("警告: 请先设置脚本中的 cookie_value 变量！")
    main()
