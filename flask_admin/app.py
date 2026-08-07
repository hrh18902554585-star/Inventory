import os
import json
import datetime
import time
from flask import Flask, render_template, request, jsonify
from query_inventory import get_inventory_query

app = Flask(__name__)
CONFIG_FILE = os.path.join(current_dir, "config.json")
COOKIE_FILE = os.path.join(current_dir, "cookie.txt")
CACHE_FILE = os.path.join(current_dir, "inventory_cache.json")

# 仓库配置：{ 显示名称: storeCodes列表(None=不限) }
WAREHOUSES = {
    "义乌": None,
    "南昌": ["NCZ801"]
}

def load_json(filepath, default):
    if os.path.exists(filepath):
        with open(filepath, 'r', encoding='utf-8') as f:
            try:
                return json.load(f)
            except:
                return default
    return default

def save_json(filepath, data):
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

def aggregate_inventory(data_list):
    """聚合库存数据：可用=非默认渠道累加，总库存和占用=所有渠道累加"""
    available_qty = 0
    total_good_qty = 0
    total_lock_qty = 0
    store_name = ""
    
    for inv in data_list:
        total_good_qty += inv.get("goodQuantity", 0)
        total_lock_qty += inv.get("lockQuantity", 0)
        if inv.get("channelName") != "默认":
            available_qty += inv.get("availableQuantity", 0)
        if not store_name and inv.get("storeName"):
            store_name = inv.get("storeName")
    
    return {
        "availableQuantity": available_qty,
        "goodQuantity": total_good_qty,
        "lockQuantity": total_lock_qty,
        "storeName": store_name or "-"
    }

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/configs', methods=['GET'])
def get_configs():
    return jsonify(load_json(CONFIG_FILE, []))

@app.route('/api/configs', methods=['POST'])
def save_configs():
    data = request.json
    save_json(CONFIG_FILE, data)
    return jsonify({"success": True})

@app.route('/api/cookie', methods=['GET'])
def get_cookie():
    cookie = ""
    if os.path.exists(COOKIE_FILE):
        with open(COOKIE_FILE, 'r', encoding='utf-8') as f:
            cookie = f.read().strip()
    return jsonify({"cookie": cookie})

@app.route('/api/cookie', methods=['POST'])
def save_cookie():
    cookie = request.json.get("cookie", "")
    with open(COOKIE_FILE, 'w', encoding='utf-8') as f:
        f.write(cookie)
    return jsonify({"success": True})

@app.route('/api/inventory/cache', methods=['GET'])
def get_inventory_cache():
    return jsonify(load_json(CACHE_FILE, {}))

@app.route('/api/inventory', methods=['POST'])
def fetch_inventory():
    data = request.json
    item_code = data.get("itemCode")
    cookie = data.get("cookie")
    
    if not item_code or not cookie:
        return jsonify({"error": "缺少商品编码或Cookie"}), 400
    
    warehouse_data = {}
    now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    any_success = False
    
    for wh_name, store_codes in WAREHOUSES.items():
        res = get_inventory_query(item_code, cookie, store_codes)
        
        if "error" not in res and res.get("data") is not None:
            data_list = res["data"]
            if len(data_list) > 0:
                agg = aggregate_inventory(data_list)
                agg["updateTime"] = now_str
                warehouse_data[wh_name] = agg
                any_success = True
            else:
                warehouse_data[wh_name] = {
                    "availableQuantity": 0,
                    "goodQuantity": 0,
                    "lockQuantity": 0,
                    "storeName": wh_name,
                    "updateTime": now_str
                }
        else:
            warehouse_data[wh_name] = {
                "availableQuantity": 0,
                "goodQuantity": 0,
                "lockQuantity": 0,
                "storeName": f"{wh_name}(查询失败)",
                "updateTime": now_str
            }
        
        # 仓库间加延迟防封
        time.sleep(0.8)
    
    # 更新缓存
    cache_data = load_json(CACHE_FILE, {})
    cache_data[item_code] = warehouse_data
    save_json(CACHE_FILE, cache_data)
    
    return jsonify({"success": any_success, "data": warehouse_data})

if __name__ == '__main__':
    # 默认运行在 5000 端口
    app.run(host='0.0.0.0', port=3000, debug=True)