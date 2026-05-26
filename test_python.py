import requests
import json

# ===================== 你需要手动修改的部分 =====================
# 请在这里替换成你自己的cookie字符串
COOKIE = r"xlly_s=1; cn_account_lang=zh_CN; x-hng=lang=zh-CN; isg=BOfnyVnGQlsoU8bXhJWnuqHydhuxbLtOfzp4WrlVlXadqA5qxjounEvrzqg2QJPG; lvt=1772432731829; cncc=fb109569514aa968c18a30bd9ccb909d; TwAhx8HL=C6BCB215B673113B88DEFEF22D0D5CD441D3D197ABA710AE36592A8446521ABF704A4A73694B4970B1A24909F661D091A53A1457C557B028E643F3FD6A9648E39F4237DD45D2D7D16297F502326F30DB3CB04FD8ED746B1B2E03282863AE59E817CDC3561B36201385CC8C2E0D9677A430C4FDB8FCA05F8E369E74A334C708D5B783B140A4856B58E704E47C67746EB42FDC758315A88B1ABADC4C2A0B142FA7C70E3191AD4A1A1884DEEF92CB4FFBA93C7F6A1F3A9E6EA26CF8575C634CF36D831C4DBCA383788679FA1670FCF949506112BD4B511581AC7CC293AD49C2F4BAB2598908D4FBE9F4CBD43D8A63686A98; SL34syaT=8C5D983BCBE6B9EFC7610EFF8ADB68A1; accountId=MTgxNjc3ODEwMzIyMw==; cacbi=MTgxNjc3ODEwMzIyMw==; cpcode=4399135568313; isLogin=true; account=Y24t6Laj5ZGz54y05rW35aSW5peX6Iiw5bqXOui0pOW+tw==; userLoginType=cic; cn-gateway-useagent=pc; bizUserId=2212853812821; cna=XRssIkF/Px4CAbcRfm9ABbQy; CURRENT_LANGUAGE=zh; x-hng=lang=zh-CN&domain=b.cainiao.com; cf_counter_nick=%E8%B6%A3%E5%91%B3%E7%8C%B4%E6%B5%B7%E5%A4%96%E6%97%97%E8%88%B0%E5%BA%97; loginType=havanaTokenSSO-TAOBAO; cnUId=1816778103223; tfstk=gjztotYXh9XGJF_CeFjhizhw4n5hZMVadRPWoxDMcJeLHv4G_lVckqeIKPDgsVMvDkN4jq2c_mwLhR1ZiPfaJ-FYFlcm5ORxkSezjcgimjLYMvhMj1oclCzLeEYGQGPXkq0fETblr5lZuq6oO0U5JdljGf_mfhgI7jY_OwScr5PwOYuAnh_lkUH3ejMbhcGIAjkI1jM_h2gIavTsGFGXd6hqdqTsCAtIObhkChibhW1KGvMjlcwjR6hqdxgjlb5dHvOsnEEphqL3inKXkEUK6cHvovYxvP8omY1tQF8ZBfn9j5MplEaLc6gt9AsytxuiQ5GT3a8Z5mEbS2a1dZg74JUxV4Ic_cNYv-ugRstsFl2imPopChG-WAn75DbROWibvy3g5t-ztWHs22qhYOmmWRErUcsFL-FKI-atAdBnnuV35De5KeeqDoaiRP6Cyg-zrzI2fLD-ih1d9n-qfXrzAC2cd0UvCXHl6ZK20D5E9Yfd9n-qfXlKE1B90noFT"

# 接口地址
API_URL = "https://b.cainiao.com/merchantchargeorder/queryChargeOrderListNew"

# POST请求参数
POST_DATA = {
    "orderNo": "YT8844569147030",
    "currentPage": 1,
    "pageSize": 10,
    "orderNoType": 0
}

# ===================== 脚本核心逻辑 =====================
def get_charge_order_list():
    """
    发送POST请求获取菜鸟充值订单列表
    """
    # 模拟浏览器的请求头（根据用户提供的信息更新）
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

    try:
        # 发送POST请求，将参数转为JSON字符串
        response = requests.post(
            url=API_URL,
            headers=headers,
            data=json.dumps(POST_DATA),  # 确保参数以JSON格式发送
            timeout=30,  # 设置超时时间，避免无限等待
            allow_redirects=False # 禁止自动重定向，以便检测登录状态
        )

        # 检查是否发生重定向（通常意味着Cookie失效）
        if response.status_code in (301, 302, 303, 307, 308):
            print(f"错误：请求被重定向到 {response.headers.get('Location')}")
            print("原因可能为：Cookie已失效或未登录。")
            print("解决方法：请重新在浏览器登录菜鸟后台，按F12打开开发者工具，复制最新的请求Cookie替换代码中的COOKIE变量。")
            return None

        # 检查响应状态码
        response.raise_for_status()

        # 检查响应内容是否为JSON
        content_type = response.headers.get('Content-Type', '')
        if 'application/json' not in content_type:
            print(f"警告：响应内容类型不是JSON ({content_type})")
            # 尝试打印前200个字符看看是什么
            print("响应内容预览:", response.text[:200])

        # 返回JSON格式的响应结果
        return response.json()

    except requests.exceptions.Timeout:
        print("错误：请求超时，请检查网络或接口是否可用")
        return None
    except requests.exceptions.HTTPError as e:
        print(f"错误：HTTP请求失败，状态码 {response.status_code}，详情：{e}")
        return None
    except requests.exceptions.RequestException as e:
        print(f"错误：请求发生异常，详情：{e}")
        return None
    except json.JSONDecodeError:
        print("错误：接口返回的不是有效的JSON格式数据")
        print("原始响应内容：", response.text)
        return None

if __name__ == "__main__":
    # 调用函数并打印结果
    result = get_charge_order_list()
    if result:
        print("接口请求成功，返回数据：")
        # 格式化输出JSON，方便阅读
        print(json.dumps(result, ensure_ascii=False, indent=4))