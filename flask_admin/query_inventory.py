import requests
import json
import re

def _extract_csrf_from_cookie(cookie):
    """从 Cookie 字符串中提取 XSRF-TOKEN"""
    match = re.search(r'XSRF-TOKEN=([a-f0-9\-]+)', cookie)
    if match:
        return match.group(1)
    return ""

def _get_common_headers(csrf_token, cookie):
    return {
        "accept": "application/json, text/plain, */*",
        "accept-language": "zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6",
        "bx-v": "2.5.36",
        "content-type": "application/json;charset=UTF-8",
        "origin": "https://b.cainiao.com",
        "referer": "https://b.cainiao.com/business/import/store/one-plate-inventory-query/warehouse-inventory-query-v2",
        "sec-ch-ua": '"Not;A=Brand";v="8", "Chromium";v="150", "Microsoft Edge";v="150"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Windows"',
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "same-origin",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36 Edg/150.0.0.0",
        "x-xsrf-token": csrf_token,
        "Cookie": cookie
    }

def get_inventory_query(item_param_code, cookie, store_codes=None):
    url = "https://b.cainiao.com/omni/inventory/itemInv/query"
    csrf_token = _extract_csrf_from_cookie(cookie)
    if not csrf_token:
        return {"error": "Cookie 中未找到 XSRF-TOKEN，请确认 Cookie 是否完整"}
    
    headers = _get_common_headers(csrf_token, cookie)
    
    post_data = {
        "filterZero": True,
        "page": 1,
        "limit": 20,
        "itemParam": [item_param_code],
        "_csrf": csrf_token
    }
    if store_codes:
        post_data["storeCodes"] = store_codes
    
    try:
        response = requests.post(url, headers=headers, data=json.dumps(post_data), timeout=30, allow_redirects=False)
        if response.status_code in (301, 302, 303, 307, 308):
            return {"error": "请求(query)被重定向 (Cookie可能已失效)"}
        if response.status_code != 200:
            return {"error": f"请求(query)失败: 状态码 {response.status_code}"}
        return response.json()
    except Exception as e:
        return {"error": f"请求(query)异常: {e}"}


def get_inventory_quantity(item_param_code, cookie):
    url = "https://b.cainiao.com/omni/inventory/itemInv/quantity"
    csrf_token = _extract_csrf_from_cookie(cookie)
    if not csrf_token:
        return {"error": "Cookie 中未找到 XSRF-TOKEN，请确认 Cookie 是否完整"}
    
    headers = _get_common_headers(csrf_token, cookie)
    
    post_data = {
        "itemParamCode": item_param_code,
        "filterZero": True,
        "itemParam": [item_param_code],
        "_csrf": csrf_token
    }
    
    try:
        response = requests.post(url, headers=headers, data=json.dumps(post_data), timeout=30, allow_redirects=False)
        if response.status_code in (301, 302, 303, 307, 308):
            return {"error": "请求(quantity)被重定向 (Cookie可能已失效)"}
        if response.status_code != 200:
            return {"error": f"请求(quantity)失败: 状态码 {response.status_code}"}
        return response.json()
    except Exception as e:
        return {"error": f"请求(quantity)异常: {e}"}
