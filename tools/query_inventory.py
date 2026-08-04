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

def get_inventory_query(item_param_code, cookie):
    """
    接口1: /omni/inventory/itemInv/query
    用于查询库存列表（包含分页参数）
    """
    url = "https://b.cainiao.com/omni/inventory/itemInv/query"
    csrf_token = _extract_csrf_from_cookie(cookie)
    if not csrf_token:
        return {"error": "Cookie 中未找到 XSRF-TOKEN，请确认 Cookie 是否完整"}
    
    headers = _get_common_headers(csrf_token, cookie)
    
    post_data = {
        "filterZero": True,
        "page": 1,
        "limit": 20,
        "itemParam": [
            item_param_code
        ],
        "_csrf": csrf_token
    }
    
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
    """
    接口2: /omni/inventory/itemInv/quantity
    用于查询特定的库存汇总/明细数据（带有 itemParamCode）
    """
    url = "https://b.cainiao.com/omni/inventory/itemInv/quantity"
    csrf_token = _extract_csrf_from_cookie(cookie)
    if not csrf_token:
        return {"error": "Cookie 中未找到 XSRF-TOKEN，请确认 Cookie 是否完整"}
    
    headers = _get_common_headers(csrf_token, cookie)
    
    post_data = {
        "itemParamCode": item_param_code,
        "filterZero": True,
        "itemParam": [
            item_param_code
        ],
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

if __name__ == "__main__":
    # 使用用户提供的测试参数
    test_code = "4891035065913"
    test_cookie = "x-hng=lang=zh-CN&domain=b.cainiao.com; cna=FdCKIijKjgsCAbcRfQYubvAS; lid=%E8%B6%A3%E5%91%B3%E7%8C%B4%E6%B5%B7%E5%A4%96%E6%97%97%E8%88%B0%E5%BA%97%3A%E8%B4%A4%E5%BE%B7; wk_cookie2=116e2170a1e9318bf6104cf2967d7ea3; wk_unb=UNN8GJd3EcSt1A%3D%3D; cn_account_lang=zh_CN; x-hng=lang=zh-CN; SL34syaT=8C5D983BCBE6B9EFC7610EFF8ADB68A1; cacbi=MTgxNjc3ODEwMzIyMw==; cpcode=4399135568313; cn-gateway-useagent=pc; XSRF-TOKEN=925d1cc7-cb61-491d-87c9-be725384be2e; FE_XSRF_TOKEN=925d1cc7-cb61-491d-87c9-be725384be2e; GOS_API_CSRF_TOKEN=74ae2521-37ca-49c5-b308-c09a2d5aa84c; dnk=; unb=2221215931284; lgc=; cookie2=15f20c541d2ebb46f887bd27504053f7; _nk_=; cancelledSubSites=empty; t=bee0b93f3812069358029e89492c7790; sn=%E8%B6%A3%E5%91%B3%E7%8C%B4%E6%B5%B7%E5%A4%96%E6%97%97%E8%88%B0%E5%BA%97%3A%E8%B4%A4%E5%BE%B7; mycnuser_inner_sid=b2fa31549e274a82bf6e9974e14a9c18; bizUserId=2212853812821; CURRENT_LANGUAGE=zh; cf_counter_nick=%E8%B6%A3%E5%91%B3%E7%8C%B4%E6%B5%B7%E5%A4%96%E6%97%97%E8%88%B0%E5%BA%97; cn-gateway-gray=1e4e72c4-2672-4bd5-ac54-de8d8d2bc9ba; xlly_s=1; _tb_token_=f6051b183bbe1; cncc=fb109569514aa968c18a30bd9ccb909d; accountId=MTgxNjc3ODEwMzIyMw==; isLogin=true; account=Y24t6Laj5ZGz54y05rW35aSW5peX6Iiw5bqXOui0pOW+tw==; userLoginType=cic; isg=BPT0I0D5IkACW7Zo36LnJmwPxbJmzRi3YS5pN45V7X8C-ZVDttuNRfH6fTEhAVAP; lvt=1785137295226; TwAhx8HL=C6BCB215B673113B88DEFEF22D0D5CD441D3D197ABA710AE36592A8446521ABF704A4A73694B4970B1A24909F661D091A53A1457C557B028E643F3FD6A9648E39F4237DD45D2D7D16297F502326F30DB0495B6E446E770FBD86255C930647F0B7C54CA97971EF4CD652981929DCF3FEC30C4FDB8FCA05F8E369E74A334C708D5B783B140A4856B58E704E47C67746EB49DA9F5B621CAD3A14EEAF22834185571613995158A2165B163A3858CBF3961FEFE55DCEFF41FE6E86B5D999E89AD3CDCC4C681A9C98ACB840F162FA032671F1E6112BD4B511581AC7CC293AD49C2F4BAB2598908D4FBE9F4CBD43D8A63686A98; JSESSIONID=44961D3FF3E1773E49781AEDF4C4AF1E; uc1=cookie14=UoYWON5CFrbRjA%3D%3D&cookie21=UIHiLt3xSalX; sgcookie=E100fLcq7qlYvT8RCN%2FwiqPuVa1aLsrkJMwgPNtEo3S5ap2INjS1w5AnzXqSkAMY4WJgyZoulM2LRMhLe7s4cdn1ozz6VaIPK8mfXzJTygeNzaozqhOQZBqvV120ljOjKyE9; csg=fd5af12e; tfstk=glMqo91jLKp2rg8nYD2wzH51bgyxhR8BSAa_jcmgcr4D6c4aQqgScnejjPuZPzKOGrGj_OoiXrmjcRgasDURhOwb1Ourr4GbiRg_Ql0QzmN_fnhaj4m1cSDZXOrijVKY5ndSDmeTIeTQQpixD1SNwqtCn8xgjljDVSjKfUTuIeTBF_suMEwifqgaD7muylWgmS0GE7q_rlf0IV4uZkqCoR2iS3yuAoWcnsXcE7qLrP2gIVmk4laumR2iS0xzXbiimcXzASxAGXC5AnLL7ym0zOXFvPNDcVf1raDz0Skgezr7VYr4gyV_PPwtn4iihxFJGsetVXuZsVdCw-oii-qIDKWzKmcSQuM6f1zmVYPtH77ciky4uWD0aptI25crU-MDW6nS4rVUFbOJl5wquXULiQL-70zjSxPluUasO0M0a2Y5UVFZ9cZZuKWm-gr1WujgKAhVS1P02uzB43Ruj_StcBvZw1CTZJEzRnZf61F02uzB435O67484ytbc"
    
    print(f"==========================================")
    print(f"正在查询库存接口1 (query)，商品编码: {test_code} ...")
    result_query = get_inventory_query(test_code, test_cookie)
    
    print("\n[query] 查询结果:")
    print(json.dumps(result_query, indent=4, ensure_ascii=False))
    print(f"\n==========================================")
    
    print(f"正在查询库存接口2 (quantity)，商品编码: {test_code} ...")
    result_quantity = get_inventory_quantity(test_code, test_cookie)
    
    print("\n[quantity] 查询结果:")
    print(json.dumps(result_quantity, indent=4, ensure_ascii=False))