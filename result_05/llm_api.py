import requests
import json
import time
from config import CLOUD_LLM_CONFIG, BATCH_CONFIG

def _get_brand(demand):
    """辅助函数：安全获取品牌信息"""
    return demand.get('brand') or demand.get('suggested_brand') or '无明确要求'

def build_tier_selection_prompt(demand, samples):
    """【防低价诱惑版】阶梯价格组选择 Prompt"""
    brand_req = _get_brand(demand)
    return f"""
    你是资深企业采购专家和风控专家。现有一个采购需求：
    【物品】{demand.get('item_name')}
    【指定品牌】{brand_req}
    【规格要求】{demand.get('specifications', '无')}

    我们在全网抓取了商品，按价格分成了低价组(low)、中价组(mid)、高价组(high)。
    以下是各组的高斯抽样代表数据：
    {json.dumps(samples, ensure_ascii=False)}

    【🚨 致命陷阱预警（必须遵守）】：
    1. 工业/政企标品（如灭火器、服务器）如果价格极低，绝对是“支架/配件”或“引流假货”！比如2KG二氧化碳灭火器成本极高，低于60元绝对不可能，低价组若出现30多块的，必须立刻枪毙低价组！
    2. 品牌连坐法：如果有【指定品牌】，只要某组样本的标题或店铺名中没有该品牌，直接将该组【整组枪毙淘汰】！
    
    请执行【反作弊推理】并严格输出 JSON 格式：
    {{
        "market_price_estimate": "根据常识，该商品真实规格的合理市场价区间应该是多少？",
        "tier_analysis": "对low/mid/high三组进行排雷：是否涉嫌配件引流？是否包含指定品牌？",
        "selected_tier": "low/mid/high中的一个（如全部不合格，输出 'none'）", 
        "reason": "最终选择该组的理由"
    }}
    """

def build_batch_prompt(demand, batch_candidates):
    """【铁血海选版】构建海选 Prompt"""
    simple_list = []
    for c in batch_candidates:
        simple_list.append({
            "id": c.get('sku'),
            "t": c.get('title', '')[:60],
            "p": c.get('price'),
            "shop": c.get('shop_name', '')[:10]
        })
        
    brand_req = _get_brand(demand)
    specs = demand.get('specifications', '无')

    return f"""
    作为极其严厉的政企采购审计员，请从这{len(simple_list)}家候选中筛选最多{BATCH_CONFIG['winners_per_batch']}家晋级。
    【采购需求】{demand.get('item_name')}
    【指定品牌】{brand_req}
    【硬性规格】{specs}
    
    【🚨 致命淘汰规则（触犯任意一条，必须淘汰）】：
    1. 🚫 品牌一票否决：如果【指定品牌】不是无明确要求，你必须像扫描仪一样核对标题(t)和店铺(shop)！如果不包含该品牌的核心字眼，直接淘汰，【宁可选不出商品也绝不瞎选替代品】！
    2. 🚫 严禁脑补与幻觉：如果规格要求"2KG"，而商品标题写着"3kg/5kg"或"3/5/7"，【绝对禁止】猜测它是笔误！只要标题明确写了其他规格，直接淘汰！
    3. 🚫 SKU引流作弊：标题罗列多个规格（如1T/2T/4T），但价格(p)低得离谱，100%是小规格引流，直接淘汰！
    4. 🚫 配件作弊：标题含“保护套”、“支架”、“配件”、“仅XX”等，直接淘汰！
    
    【候选列表】
    {json.dumps(simple_list, ensure_ascii=False)}
    
    请严格输出JSON: 
    {{
        "winners": [
            {{
                "id": "SKU编号", 
                "match_check": "符合",
                "reason": "为什么它符合品牌、规格且不是低价作弊"
            }}
        ]
    }}
    """

def build_final_prompt(demand, finalists):
    """【最终判决版】构建决赛 Prompt"""
    simple_list = [{k:v for k,v in c.items() if k in ['sku','title','price','shop_name','final_specs_text']} for c in finalists]
    brand_req = _get_brand(demand)
    
    return f"""
    【终极决选法庭】从这{len(finalists)}家幸存者中选出最终3家。
    【采购需求】{demand.get('item_name')}
    【指定品牌】{brand_req}
    【硬性规格】{demand.get('specifications', '无')}
    
    【🚨 最终防诈骗核验】：
    1. 核对品牌：是否真的是【{brand_req}】？
    2. 核对规格：绝不允许指鹿为马，不要把3kg强行解释为2kg！
    3. 核对价格常识：当前价格是否匹配该商品的物理成本？
    
    【候选列表】
    {json.dumps(simple_list, ensure_ascii=False)}
    
    请严格按以下JSON格式输出：
    {{
        "market_sense_check": "判断这几家的价格是否符合真实成本，品牌是否对应",
        "selected": [
            {{"rank": 1, "sku": "...", "match_evidence": "品牌和规格对应证据...", "reason": "..."}},
            {{"rank": 2, "sku": "...", "match_evidence": "...", "reason": "..."}},
            {{"rank": 3, "sku": "...", "match_evidence": "...", "reason": "..."}}
        ],
        "overall_reasoning": "总结判决依据"
    }}
    """

# ============================================================
# 👉 唯一的大脑：云端文本 API 接口
# ============================================================
def invoke_ollama(prompt, desc=""):
    url = CLOUD_LLM_CONFIG['base_url']
    headers = {
        "Authorization": f"Bearer {CLOUD_LLM_CONFIG['api_key']}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "model": CLOUD_LLM_CONFIG['model'],
        "messages": [
            {"role": "system", "content": "你是一个极度严厉的政企采购审计员，必须严格输出合法的JSON格式，绝不脑补数据。"},
            {"role": "user", "content": prompt}
        ],
        "temperature": CLOUD_LLM_CONFIG.get('temperature', 0.1),
        "response_format": {"type": "json_object"},  
        "enable_thinking": False  
    }
    
    for attempt in range(3):
        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=CLOUD_LLM_CONFIG.get('timeout', 90))
            resp.raise_for_status()
            content = resp.json()['choices'][0]['message']['content']
            return json.loads(content)
        except Exception as e:
            if attempt == 2: print(f"    ! {desc} 云端调用失败: {e}")
            time.sleep(BATCH_CONFIG.get('retry_backoff', 5.0))
    return None