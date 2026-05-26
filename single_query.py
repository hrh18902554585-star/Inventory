import requests
import json

# ===================== 配置部分 =====================
# 从 gui_batch_query.py 复制的 Cookie
COOKIE = r"loginType=havanaTokenSSO-TAOBAO; cnUId=1816778103223; xlly_s=1; cna=XRssIkF/Px4CAbcRfm9ABbQy; x-hng=lang=zh-CN&domain=b.cainiao.com; cn-gateway-useagent=pc; CURRENT_LANGUAGE=zh; cn_account_lang=zh_CN; x-hng=lang=zh-CN; isg=BDIyaRlhj-s98rPUAWraSSzVg3gUwzZdAr1tGfwLGOXQj9OJ5Fdsb0msfysz_671; lvt=1772529110250; cncc=fb109569514aa968c18a30bd9ccb909d; TwAhx8HL=C6BCB215B673113B88DEFEF22D0D5CD441D3D197ABA710AE36592A8446521ABF704A4A73694B4970B1A24909F661D091A53A1457C557B028E643F3FD6A9648E39F4237DD45D2D7D16297F502326F30DBD650EE31DCEF1BF72C1B1F6953FF986554DDC50A01960D2BEF4DE8B96C6B6CA130C4FDB8FCA05F8E369E74A334C708D5B783B140A4856B58E704E47C67746EB45C90FA61439CB9B6D1C169F4491AB96E703B6E0BD5055E5962CB4592DDAA6FF18EA4FEDF1425D82F19C667AE54EEABFC37C10ECA0D1E8F747E1EA39ADB261FA56112BD4B511581AC7CC293AD49C2F4BAB2598908D4FBE9F4CBD43D8A63686A98; SL34syaT=8C5D983BCBE6B9EFC7610EFF8ADB68A1; accountId=MTgxNjc3ODEwMzIyMw==; cacbi=MTgxNjc3ODEwMzIyMw==; cpcode=4399135568313; isLogin=true; account=Y24t6Laj5ZGz54y05rW35aSW5peX6Iiw5bqXOui0pOW+tw==; userLoginType=cic; bizUserId=2212853812821; cf_counter_nick=%E8%B6%A3%E5%91%B3%E7%8C%B4%E6%B5%B7%E5%A4%96%E6%97%97%E8%88%B0%E5%BA%97; tfstk=gGQIoXD8yvDCqjVLevPZhnhKgZTWR5z4JbORi_3EweLpVG6RF6-PYkX5fTBMYpe3ZOJR3OLPY38pFb6Pa9SF9e-JNt5ypw7zx3H53d9ea8VH2N1PGMRrYasiPsfl8WYztefHrUe43ryVt6YkTAxqjwTO6Bf99X38bFh0LDVz3rzV9ATgyXeVYSgfRQOJyBpJ2FF6aQmJyHKK65OJavn-JTCT1dASvQ3JyCp9iImpyUBR65OkBBLJvTCT1Qv9ebSxGQZBK6N5arZfsxF1Odg-yNOTEKfIr4R1JBaWh69_H-QsoH9A9dg8dvKAXL9GkRr1stsdLCX7lRTAmO_WDUaInBsOGFpekoi6R1WhleQbd2RwSp-A2hNLJ1TBdnA6DbipRgBhPHjIZSf9JOjDnHEgIC_Fu39DfAed_19pcg6UI4pFc1B60NkZuEIcCatvkgoSuKG680G6m4O635Nsq0fPl6PZgIFe9HdMOhP_1vIkvCA635Nsq0xpsBO415Mdq"

# 接口地址
API_URL = "https://b.cainiao.com/merchantchargeorder/queryChargeOrderListNew"

def get_charge_order_list(order_no):
    """
    发送POST请求获取菜鸟充值订单列表
    """
    # 模拟浏览器的请求头
    headers = {
        "accept": "application/json, text/plain, */*",
        "bx-v": "2.5.36",
        "content-type": "application/json",
        "h-csrf": "635e77ca-003a-498a-9a58-18c213306b08",
        "referer": "https://b.cainiao.com/cf_seller/charge-order/charge-order-query",
        "sec-ch-ua": '"Not:A-Brand";v="99", "Microsoft Edge";v="145", "Chromium";v="145"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Windows"',
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36 Edg/145.0.0.0",
        "Cookie": COOKIE
    }

    # POST请求参数
    post_data = {
        "orderNo": order_no,
        "currentPage": 1,
        "pageSize": 10,
        "orderNoType": 0
    }

    try:
        # 发送POST请求
        response = requests.post(
            url=API_URL,
            headers=headers,
            data=json.dumps(post_data),
            timeout=30,
            allow_redirects=False
        )

        # 检查是否发生重定向
        if response.status_code in (301, 302, 303, 307, 308):
            return {"error": f"请求被重定向 (Cookie可能失效)"}

        # 检查响应状态码
        if response.status_code != 200:
            return {"error": f"请求失败: 状态码 {response.status_code}"}

        return response.json()

    except Exception as e:
        return {"error": f"请求异常: {e}"}

def query_single_order():
    print("=" * 50)
    print("菜鸟充值订单单号查询工具")
    print("输入 'q' 或 'exit' 退出程序")
    print("=" * 50)

    while True:
        order_no = input("\n请输入快递单号: ").strip()
        
        if not order_no:
            continue
            
        if order_no.lower() in ('q', 'exit'):
            break
            
        print(f"正在查询单号: {order_no} ...")
        
        result = get_charge_order_list(order_no)
        
        total_quoted_amount = 0.0
        msg = ""
        
        if result and "error" not in result:
            if result.get("success") and result.get("data"):
                data_list = result.get("data")
                if isinstance(data_list, list):
                    count = 0
                    print("-" * 30)
                    for item in data_list:
                        amount = item.get("quotedAmount")
                        business_type = item.get("businessTypeDesc", "未知类型")
                        status = item.get("statusDesc", "未知状态")
                        
                        if amount:
                            amount_float = float(amount)
                            total_quoted_amount += amount_float
                            count += 1
                            print(f"  > 记录 {count}: 金额={amount_float}, 类型={business_type}, 状态={status}")
                
                # 保留两位小数
                total_quoted_amount = round(total_quoted_amount, 2)
                print("-" * 30)
                print(f"✅ 查询成功！")
                print(f"💰 总计 quotedAmount: {total_quoted_amount}")
            else:
                print("⚠️ 查询无数据")
        else:
            error_msg = result.get("error") if result else "未知错误"
            print(f"❌ 查询失败: {error_msg}")

if __name__ == "__main__":
    query_single_order()
