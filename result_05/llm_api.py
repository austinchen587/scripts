import requests
import json
import time
from config import OLLAMA_CONFIG, BATCH_CONFIG

def build_batch_prompt(demand, batch_candidates):
    """构建海选 Prompt"""
    simple_list = []
    for c in batch_candidates:
        simple_list.append({
            "sku": c.get('sku'),
            "title": c.get('title', '')[:40],
            "price": c.get('price'),
            "sales": c.get('sales'),
            "shop": c.get('shop_name', '')[:8],
            "info": c.get('hot_info', '')[:10]
        })
    return f"""
    作为采购专家，请从这{len(simple_list)}家候选中筛选{BATCH_CONFIG['winners_per_batch']}家晋级。
    【需求】{demand.get('item_name')}
    【规则】1.符合需求(最重要) 2.价格低 3.销量高
    【列表】
    {json.dumps(simple_list, ensure_ascii=False)}
    请严格输出JSON: {{"winners": [{{"sku": "...", "reason": "..."}}]}}
    """

def build_final_prompt(demand, finalists):
    """构建决赛 Prompt"""
    simple_list = [{k:v for k,v in c.items() if k in ['sku','title','price','sales','shop_name']} for c in finalists]
    return f"""
    【终极决选】从这{len(finalists)}家优胜者中选出最终3家。
    【需求】{demand.get('item_name')}
    【规则】1.必须符合规格 2.价格最低优先 3.参考销量评价
    【列表】
    {json.dumps(simple_list, ensure_ascii=False)}
    请输出JSON:
    {{
        "selected": [
            {{"rank": 1, "sku": "...", "reason": "..."}},
            {{"rank": 2, "sku": "...", "reason": "..."}},
            {{"rank": 3, "sku": "...", "reason": "..."}}
        ],
        "overall_reasoning": "总结"
    }}
    """

def invoke_ollama(prompt, desc=""):
    """底层API调用，含重试"""
    url = f"{OLLAMA_CONFIG['base_url']}/api/chat"
    payload = {
        "model": OLLAMA_CONFIG['model'],
        "messages": [{"role": "user", "content": prompt}],
        "format": "json", "stream": False
    }
    for attempt in range(3):
        try:
            resp = requests.post(url, json=payload, timeout=OLLAMA_CONFIG['timeout'])
            resp.raise_for_status()
            return json.loads(resp.json()['message']['content'])
        except Exception as e:
            if attempt == 2: print(f"    ! {desc} 失败: {e}")
            time.sleep(BATCH_CONFIG['retry_backoff'])
    return None