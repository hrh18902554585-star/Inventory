import requests
import json
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from queue import Queue
from datetime import datetime

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


def get_inventory_quantity(item_param_code, cookie, thread_id=0, delay=0):
    """
    单个查询库存数量的函数
    :param item_param_code: 商品参数编码
    :param cookie: Cookie字符串
    :param thread_id: 线程ID，用于标识
    :param delay: 启动延迟（秒）
    """
    # 如果设置了延迟，则等待
    if delay > 0:
        time.sleep(delay)
    
    url = "https://b.cainiao.com/omni/inventory/itemInv/quantity"
    csrf_token = _extract_csrf_from_cookie(cookie)
    if not csrf_token:
        return {"error": "Cookie 中未找到 XSRF-TOKEN，请确认 Cookie 是否完整", "thread_id": thread_id}
    
    headers = _get_common_headers(csrf_token, cookie)
    
    post_data = {
        "itemParamCode": item_param_code,
        "filterZero": True,
        "itemParam": [item_param_code],
        "_csrf": csrf_token
    }
    
    try:
        start_time = time.time()
        response = requests.post(url, headers=headers, data=json.dumps(post_data), timeout=30, allow_redirects=False)
        elapsed_time = time.time() - start_time
        
        if response.status_code in (301, 302, 303, 307, 308):
            return {"error": "请求(quantity)被重定向 (Cookie可能已失效)", "thread_id": thread_id, "elapsed": elapsed_time}
        if response.status_code != 200:
            return {"error": f"请求(quantity)失败: 状态码 {response.status_code}", "thread_id": thread_id, "elapsed": elapsed_time}
        
        result = response.json()
        result["thread_id"] = thread_id
        result["elapsed"] = elapsed_time
        return result
    except Exception as e:
        return {"error": f"请求(quantity)异常: {e}", "thread_id": thread_id}


def batch_get_inventory_quantity(item_param_codes, cookie, max_workers=10, delay_between=0.1):
    """
    批量查询库存数量（多线程）
    :param item_param_codes: 商品参数编码列表
    :param cookie: Cookie字符串
    :param max_workers: 最大线程数，默认10
    :param delay_between: 每个线程启动间隔（秒），默认0.1秒
    :return: 包含所有结果的列表
    """
    results = []
    
    # 使用线程池
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # 提交所有任务，每个任务有不同的启动延迟
        future_to_param = {}
        for i, item_code in enumerate(item_param_codes):
            # 计算延迟：每个线程间隔 delay_between 秒
            delay = i * delay_between
            future = executor.submit(get_inventory_quantity, item_code, cookie, i, delay)
            future_to_param[future] = item_code
        
        # 收集结果
        for future in as_completed(future_to_param):
            item_code = future_to_param[future]
            try:
                result = future.result()
                result["item_param_code"] = item_code
                results.append(result)
                print(f"完成: {item_code} (线程 {result.get('thread_id', 'N/A')}) - 耗时: {result.get('elapsed', 0):.2f}秒")
            except Exception as e:
                results.append({
                    "item_param_code": item_code,
                    "error": f"线程执行异常: {e}"
                })
    
    return results


def batch_get_inventory_quantity_with_queue(item_param_codes, cookie, max_workers=10, delay_between=0.1):
    """
    使用队列方式批量查询库存数量（更精确控制启动间隔）
    :param item_param_codes: 商品参数编码列表
    :param cookie: Cookie字符串
    :param max_workers: 最大线程数，默认10
    :param delay_between: 每个线程启动间隔（秒），默认0.1秒
    :return: 包含所有结果的列表
    """
    results = []
    results_lock = threading.Lock()
    task_queue = Queue()
    
    # 将所有任务放入队列
    for i, item_code in enumerate(item_param_codes):
        task_queue.put((i, item_code, i * delay_between))
    
    def worker():
        """工作线程函数"""
        while not task_queue.empty():
            try:
                thread_id, item_code, delay = task_queue.get(timeout=1)
                result = get_inventory_quantity(item_code, cookie, thread_id, delay)
                result["item_param_code"] = item_code
                
                with results_lock:
                    results.append(result)
                
                print(f"完成: {item_code} (线程 {thread_id}) - 耗时: {result.get('elapsed', 0):.2f}秒")
                task_queue.task_done()
            except Exception as e:
                print(f"工作线程异常: {e}")
                break
    
    # 创建并启动工作线程
    threads = []
    for i in range(min(max_workers, len(item_param_codes))):
        t = threading.Thread(target=worker)
        t.daemon = True
        t.start()
        threads.append(t)
        # 线程启动间隔
        time.sleep(0.05)  # 线程启动本身也稍微间隔一下
    
    # 等待所有任务完成
    task_queue.join()
    
    # 等待所有线程结束
    for t in threads:
        t.join(timeout=5)
    
    return results


# 使用示例
if __name__ == "__main__":
    # 示例Cookie（请替换为实际Cookie）
    cookie = "你的Cookie字符串"
    
    # 需要查询的商品参数编码列表
    item_codes = ["code1", "code2", "code3", "code4", "code5"]  # 替换为实际编码
    
    # 方式1：使用ThreadPoolExecutor
    print("=== 使用 ThreadPoolExecutor 方式 ===")
    start_time = time.time()
    results = batch_get_inventory_quantity(
        item_param_codes=item_codes,
        cookie=cookie,
        max_workers=10,
        delay_between=0.1
    )
    total_time = time.time() - start_time
    
    print(f"\n总耗时: {total_time:.2f}秒")
    print(f"成功: {len([r for r in results if 'error' not in r])} 个")
    print(f"失败: {len([r for r in results if 'error' in r])} 个")
    
    # 打印结果
    for result in results:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    
    print("\n" + "="*50 + "\n")
    
    # 方式2：使用队列方式
    print("=== 使用队列方式 ===")
    start_time = time.time()
    results = batch_get_inventory_quantity_with_queue(
        item_param_codes=item_codes,
        cookie=cookie,
        max_workers=10,
        delay_between=0.1
    )
    total_time = time.time() - start_time
    
    print(f"\n总耗时: {total_time:.2f}秒")
    print(f"成功: {len([r for r in results if 'error' not in r])} 个")
    print(f"失败: {len([r for r in results if 'error' in r])} 个")