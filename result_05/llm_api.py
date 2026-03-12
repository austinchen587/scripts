import requests
import json
import time
# 引入新的配置 
from config import CLOUD_LLM_CONFIG, BATCH_CONFIG

def build_batch_prompt(demand, batch_candidates):
    """构建海选 Prompt (保持原样即可)"""
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
    """构建决赛 Prompt (保持原样即可)"""
    simple_list = []
    for c in finalists:
        simple_list.append({
            "sku": c.get('sku'),
            "title": c.get('title', ''), 
            "price": c.get('price'), 
            "sales": c.get('sales'),
            "shop": c.get('shop_name')
        })
    
    return f"""
    【终极决选】从这{len(finalists)}家优胜者中选出最终3家。
    【需求】{demand.get('item_name')}
    【规格要求】：{demand.get('specifications', '无')}
    【硬性规则】：
    1. 必须完全符合需求规格。
    2. 🚨【重点防骗】：注意识别列表页标题中的“配件”、“外壳”等引流词，直接淘汰！
    3. 在参数正确的前提下，价格最低优先，参考销量评价。
    【候选列表】
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

# ============================================================
# 👉 [核心修改] 唯一的大脑：云端文本 API 接口
# ============================================================
def invoke_ollama(prompt, desc=""):
    """底层API调用，已升级为云端API，函数名保留以兼容上层"""
    url = CLOUD_LLM_CONFIG['base_url']
    headers = {
        "Authorization": f"Bearer {CLOUD_LLM_CONFIG['api_key']}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "model": CLOUD_LLM_CONFIG['model'],
        "messages": [
            {"role": "system", "content": "你是一个严谨的政企采购AI，必须严格输出合法的JSON格式。"},
            {"role": "user", "content": prompt}
        ],
        "temperature": CLOUD_LLM_CONFIG.get('temperature', 0.1),
        "response_format": {"type": "json_object"},  # 强制输出 JSON
        "enable_thinking": False  # 👈 [新增] 明确关闭思考模式，加快速度并收敛逻辑
    }
    
    for attempt in range(3):
        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=CLOUD_LLM_CONFIG['timeout'])
            resp.raise_for_status()
            # 标准化提取大模型回答
            content = resp.json()['choices'][0]['message']['content']
            return json.loads(content)
        except Exception as e:
            if attempt == 2: print(f"    ! {desc} 云端调用失败: {e}")
            time.sleep(BATCH_CONFIG.get('retry_backoff', 5.0)) # [cite: 1]
    return None