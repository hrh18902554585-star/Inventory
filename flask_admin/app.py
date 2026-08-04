import os
import json
import sys
import datetime
from flask import Flask, render_template, request, jsonify

# 将上级目录加入 sys.path，以便能够导入 tools 里的脚本
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
if parent_dir not in sys.path:
    sys.path.append(parent_dir)

from tools.query_inventory import get_inventory_query

app = Flask(__name__)
CONFIG_FILE = os.path.join(current_dir, "config.json")
COOKIE_FILE = os.path.join(current_dir, "cookie.txt")
CACHE_FILE = os.path.join(current_dir, "inventory_cache.json")

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
        
    res = get_inventory_query(item_code, cookie)
    
    # 如果查询成功，更新缓存
    if "error" not in res and res.get("data") and len(res["data"]) > 0:
        data_list = res["data"]
        
        # 聚合逻辑：
        # 可用库存 = “非淘ToC” 渠道的 availableQuantity (如果没有非淘ToC，暂取所有非默认渠道的累加)
        # 总正品库存 = 所有渠道的 goodQuantity 累加
        # 占用库存 = 所有渠道的 lockQuantity 累加
        # 仓库名称 = 取第一个非空 storeName
        
        available_qty = 0
        total_good_qty = 0
        total_lock_qty = 0
        store_name = ""
        
        for inv in data_list:
            # 累加总库存和占用库存
            total_good_qty += inv.get("goodQuantity", 0)
            total_lock_qty += inv.get("lockQuantity", 0)
            
            # 提取可用库存 (非淘ToC渠道)
            # 有些商品可能没有"非淘ToC"而有"淘系ToC"等，保险起见，我们排除"默认"渠道作为可用库存的统计来源
            if inv.get("channelName") != "默认":
                available_qty += inv.get("availableQuantity", 0)
                
            if not store_name and inv.get("storeName"):
                store_name = inv.get("storeName")

        cache_data = load_json(CACHE_FILE, {})
        cache_data[item_code] = {
            "availableQuantity": available_qty,
            "goodQuantity": total_good_qty,
            "lockQuantity": total_lock_qty,
            "storeName": store_name,
            "updateTime": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        save_json(CACHE_FILE, cache_data)
        return jsonify({"success": True, "data": cache_data[item_code]})
    elif "error" not in res and (not res.get("data") or len(res["data"]) == 0):
        # 查到了但是空数据
        cache_data = load_json(CACHE_FILE, {})
        cache_data[item_code] = {
            "availableQuantity": 0,
            "goodQuantity": 0,
            "lockQuantity": 0,
            "storeName": "-",
            "updateTime": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        save_json(CACHE_FILE, cache_data)
        return jsonify({"success": True, "data": cache_data[item_code]})
        
    return jsonify(res)

if __name__ == '__main__':
    # 默认运行在 5000 端口
    app.run(host='0.0.0.0', port=3000, debug=True)