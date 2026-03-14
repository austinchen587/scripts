import requests
import json
import time
import re
from config import CLOUD_LLM_CONFIG, BATCH_CONFIG

def _get_brand(demand):
    """辅助函数：安全获取品牌信息"""
    return demand.get('brand') or demand.get('suggested_brand') or '无明确要求'

def _extract_budget_and_reqs(demand):
    """智能提取总预算、采购数量和商务特殊要求"""
    qty = 1.0
    q_str = str(demand.get('quantity', demand.get('采购数量', 1)))
    q_match = re.search(r'(\d+(?:\.\d+)?)', q_str)
    if q_match: 
        qty = float(q_match.group(1))

    budget = 0.0
    # 在所有可能的文本中寻找预算数字
    text_to_search = str(demand.get('price_display', '')) + " " + str(demand.get('notes', '')) + " " + str(demand.get('备注', ''))
    b_match = re.search(r'(?:预算|总价|price_display).*?(\d+(?:\.\d+)?)\s*(万)?元?', text_to_search, re.IGNORECASE)
    if not b_match:
        b_match = re.search(r'(\d+(?:\.\d+)?)\s*(万)?元', text_to_search)

    if b_match:
        val = float(b_match.group(1))
        if b_match.group(2) == '万' or '万' in b_match.group(0):
            val *= 10000
        budget = val
        
    # 提取需要特别提醒的商务要求（如质保、安装、发票）
    business_reqs = str(demand.get('business_reqs', demand.get('business_items', '无特别商务要求')))
    if len(business_reqs) < 5 and 'notes' in demand:
        business_reqs = str(demand.get('notes', ''))
        
    return budget, qty, business_reqs


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
    1. 工业/政企标品如果价格极低，绝对是“支架/配件”或“引流假货”！必须立刻枪毙低价组！
    2. 品牌连坐法：如果有【指定品牌】，只要某组样本没有该品牌，直接将该组整组枪毙！
    
    请严格输出 JSON 格式：
    {{
        "market_price_estimate": "根据常识的合理市场价区间",
        "tier_analysis": "对三组进行排雷分析",
        "selected_tier": "low/mid/high中的一个（或'none'）"
    }}
    """

def build_batch_prompt(demand, batch, round_num, batch_idx):
    """【防幻觉版】海选 Prompt"""
    simple_list = []
    for c in batch:
        simple_list.append({
            "id": c.get('sku'),
            "t": c.get('title', '')[:60],
            "p": c.get('price'),
            "shop": c.get('shop_name', '')[:10]
        })
    brand_req = _get_brand(demand)
    return f"""
    【海选阶段】第 {round_num} 轮，第 {batch_idx} 批次
    【采购需求】{demand.get('item_name')}
    【指定品牌】{brand_req}
    【硬性规格】{demand.get('specifications', '无')}
    
    【🚨 审计法则】：
    1. 拒绝引流低价：有“支架、配件”等字眼直接淘汰！
    2. 🚫 严禁脑补与幻觉：规格绝对禁止猜测笔误！
    3. 品牌必须吻合！

    候选列表：
    {json.dumps(simple_list, ensure_ascii=False)}

    请淘汰不合格者，严格输出 JSON 格式：
    {{
        "analysis": "简要淘汰原因",
        "survivors": ["sku1", "sku2"] 
    }}
    """

def build_final_prompt(demand, finalists):
    """【最终判决版】财务核算预警与项目风险提醒（仅评估，不强制淘汰）"""
    simple_list = [{k:v for k,v in c.items() if k in ['sku','title','price','shop_name','final_specs_text']} for c in finalists]
    brand_req = _get_brand(demand)
    
    budget, qty, business_reqs = _extract_budget_and_reqs(demand)
    
    finance_str = "无明确项目总控制预算，请基于市场常识评估单价。"
    if budget > 0:
        max_unit_price = (budget / 1.15) / qty
        finance_str = f"【💰 财务评估基准】\n" \
                      f"甲方总预算：{budget:.2f}元 | 采购数量：{qty} | 安全红线：为保证15%毛利，单价应低于 {max_unit_price:.2f} 元。"

    return f"""
    【终极决选法庭】从这{len(finalists)}家幸存者中选出最终3家。
    【采购需求】{demand.get('item_name')}
    【指定品牌】{brand_req}
    【采购数量】{qty}
    【商务特殊要求】{business_reqs}
    
    {finance_str}
    
    【🚨 最终核验指令】：
    1. 规格与品牌：这是核心！选出的3家必须符合品牌和规格要求，绝不允许指鹿为马。
    2. 价格态度：【绝对不要因为价格超过安全红线就强制淘汰商品】！你的任务是选出最优质的Top 3，然后在最后的结论中客观算账。决策权留给人类。
    
    【候选列表】
    {json.dumps(simple_list, ensure_ascii=False)}
    
    请严格按以下JSON格式输出（拒绝废话，只需核心数据）：
    {{
        "market_sense_check": "简要评估这批商品的价格行情",
        "selected": [
            {{"rank": 1, "sku": "...", "match_evidence": "品牌规格验证", "reason": "..."}},
            {{"rank": 2, "sku": "...", "match_evidence": "...", "reason": "..."}},
            {{"rank": 3, "sku": "...", "match_evidence": "...", "reason": "..."}}
        ],
        "overall_reasoning": "【精简输出】：\\n1. 财务核算与告警：列出算式(Top1单价×数量×1.15毛利率=预估成本)。对比总控制预算得出结论。如果超标，请务必输出红色预警：'⚠️ 成本超标，面临亏本风险，建议人工核实或点击重新寻源'。\\n2. 项目风险提醒：提炼【商务特殊要求】中的隐性成本(如包安装、质保期等)进行履约风险提示。"
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
            {"role": "system", "content": "你是一个极度严苛且懂算账的政企采购财务总监，必须严格输出合法的JSON，拒绝在整体结论中写无用的废话。"},
            {"role": "user", "content": prompt}
        ],
        "temperature": CLOUD_LLM_CONFIG.get('temperature', 0.1),
        "response_format": {"type": "json_object"},  
        "enable_thinking": False  
    }
    
    for attempt in range(3):
        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=CLOUD_LLM_CONFIG.get('timeout', 120))
            resp.raise_for_status()
            
            result_json = resp.json()
            if 'choices' in result_json and len(result_json['choices']) > 0:
                content = result_json['choices'][0]['message']['content']
                return json.loads(content)
        except Exception as e:
            if attempt == 2:
                print(f"    ! {desc} 云端调用失败: {e}")
                return None
            time.sleep(BATCH_CONFIG.get('retry_backoff', 5.0))
    return None