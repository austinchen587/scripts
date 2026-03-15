import requests
import json
import time
import re
from config import CLOUD_LLM_CONFIG, BATCH_CONFIG

def _get_brand(demand):
    return demand.get('brand') or demand.get('suggested_brand') or '无明确要求'

def _extract_budget_and_reqs(demand):
    budget = 0.0
    text_to_search = str(demand.get('price_display', '')) + " " + str(demand.get('notes', '')) + " " + str(demand.get('备注', ''))
    b_match = re.search(r'(?:预算|总价|price_display).*?(\d+(?:\.\d+)?)\s*(万)?元?', text_to_search, re.IGNORECASE)
    if not b_match:
        b_match = re.search(r'(\d+(?:\.\d+)?)\s*(万)?元', text_to_search)
    if b_match:
        val = float(b_match.group(1))
        if b_match.group(2) == '万' or '万' in b_match.group(0):
            val *= 10000
        budget = val
        
    business_reqs = str(demand.get('business_reqs', demand.get('business_items', '无特别商务要求')))
    if len(business_reqs) < 5 and 'notes' in demand:
        business_reqs = str(demand.get('notes', ''))
        
    return budget, business_reqs


def build_tier_selection_prompt(demand, samples):
    """【全品类动态自适应版】阶梯价格组选择"""
    brand_req = _get_brand(demand)
    
    return f"""
    你是资深政企采购风控专家，需应对从“几万元的大型设备”到“几毛钱的办公文具”等各种繁杂类目。
    现有一个采购需求：
    【物品】{demand.get('item_name')}
    【指定品牌】{brand_req}
    【规格要求】{demand.get('specifications', '无')}

    我们在全网抓取了商品，按价格分成了低价组(low)、中价组(mid)、高价组(high)。
    抽样数据如下：
    {json.dumps(samples, ensure_ascii=False)}

    【🚨 动态风控与排雷法则（看菜下饭）】：
    1. 研判商品属性：请先思考该需求是“高价值主机/设备”、“低值易耗品/文具”、还是“配件/耗材/服务”。
    2. 防“挂羊头卖狗肉”：如果需求是买“高价值主机”（如大屏、电脑），而某组价格极低，且标题充斥着“支架、配件、定金、尾款、适用”，这绝对是低价引流陷阱，该组直接枪毙！
    3. 动态豁免：如果采购需求本身就是要买【配件、支架、兼容耗材】，请允许包含这些词的组存活，绝不能误杀！如果是低值易耗品（如纸巾、螺丝），低价是常态，请合理保留。
    4. 品牌碰瓷打假：如果需求指定了明确的品牌，而某组标题写着“适用XXX、兼容XXX”（除非需求明确要兼容件），这就是山寨碰瓷，该组直接淘汰！
    
    请严格输出 JSON 格式：
    {{
        "market_price_estimate": "结合商品属性和常识，推断真实商品的合理市场价区间",
        "tier_analysis": "逐一对low/mid/high三组进行动态排雷，指出谁在搞引流作弊，谁是合理价格",
        "selected_tier": "low/mid/high中的一个（选择价格最便宜且确认为真货的组。如全都是引流作弊，输出 'none'）"
    }}
    """

def build_batch_prompt(demand, batch, round_num, batch_idx):
    """【动态逆向SEO+销量优选】海选"""
    simple_list = []
    for c in batch:
        simple_list.append({
            "id": c.get('sku'),
            "t": c.get('title', '')[:80],
            "p": c.get('price'),
            "sales": c.get('sales', '0'),
            "shop": c.get('shop_name', '')[:15]
        })
    brand_req = _get_brand(demand)

    return f"""
    【海选阶段】第 {round_num} 轮，第 {batch_idx} 批次
    【采购需求】{demand.get('item_name')}
    【指定品牌】{brand_req}
    【硬性规格】{demand.get('specifications', '无')}
    
    【🚨 动态审计与优选法则】：
    1. 动态逆向SEO识别：分析商家是否在“挂羊头卖狗肉”。如果我们要买“整机/正品”，标题里带有“支架/配件/兼容/适用/定金/尾款/仅XX”的低价引流SKU直接淘汰！但如果我们的需求本来就是买“配件”或“兼容耗材”，请准确放行相关词汇！
    2. ⚠️【多规格“起步价”陷阱】（核心排雷）：如果标题罗列了多个容量/尺寸（例如“1T/2T/4T”、“55寸/65寸/75寸”、“起”），你必须认定当前显示的价格(p)是【最低配置】的价格！如果我们的需求是高配（如4T），而价格只够买低配（如900元），这绝对是“低配引流高配”作弊，直接枪毙淘汰！绝不姑息！
    3. 规格与品牌死线：规格严重不符，或假冒指定品牌者，直接淘汰！
    4. 优选策略：在确认为真实所需商品的前提下，优先保留【价格合理且偏低】且【销量(sales)较好/店铺正规】的商品。

    候选列表：
    {json.dumps(simple_list, ensure_ascii=False)}

    请严格输出 JSON 格式：
    {{
        "analysis": "简要的排雷分析与淘汰原因",
        "survivors": ["sku1", "sku2"] 
    }}
    """

def build_final_prompt(demand, finalists):
    """【终极决选版】不强卡价格，客观算账与优选"""
    simple_list = [{k:v for k,v in c.items() if k in ['sku','title','price','shop_name','sales']} for c in finalists]
    brand_req = _get_brand(demand)
    budget, business_reqs = _extract_budget_and_reqs(demand)
    
    qty = float(demand.get('quantity', demand.get('采购数量', 1)))
    budget_str = f"甲方该项目的总控制预算为：{budget}元" if budget > 0 else "无明确项目总控制预算"

    return f"""
    【终极决选法庭】从这{len(finalists)}家幸存者中选出最完美的3家。
    【采购需求】{demand.get('item_name')}
    【指定品牌】{brand_req}
    【采购数量】{qty}
    【商务特殊要求】{business_reqs}
    【全局财务信息】{budget_str}
    
    【🏆 选品终极三维法则】：
    1. ⚠️ 最后一遍核查【起步价陷阱】：决选名单中如果还有标题写着“1T/2T/4T”但价格极低（只够买低配）的“多规格引流款”，必须动用常识将其淘汰。确保选出的商品价格能真实买到需求规格！
    2. 第一权重：在确认商品为真（非配件引流）且规格精准对应的前提下，价格最具竞争力（成本越低，利润空间越大）。
    3. 第二权重：销量口碑较好，或店铺名称更正规（如旗舰店、专卖店、自营优先）。
    注意：不要因为单价高出总预算均值就强行淘汰商品，你的任务是选出真实匹配的好东西，并把算账工作留在报告里。
    
    【候选列表】
    {json.dumps(simple_list, ensure_ascii=False)}
    
    请严格按以下JSON格式输出：
    {{
        "market_sense_check": "简述这几款入围商品的真实性、有无多规格起步价作弊、以及性价比和销量口碑情况",
        "selected": [
            {{"rank": 1, "sku": "...", "match_evidence": "为何该商品是正品且性价比最高", "reason": "..."}},
            {{"rank": 2, "sku": "...", "match_evidence": "...", "reason": "..."}},
            {{"rank": 3, "sku": "...", "match_evidence": "...", "reason": "..."}}
        ],
        "overall_reasoning": "【精简输出】：\n1. 财务核算与告警：列出算式(Top1单价×数量×1.15毛利率=预估采购总价)。如有总控制预算，比较并明确结论(是否有超预算亏本风险，如亏本请输出红色预警让人工核查)。\n2. 项目风险提醒：提炼【商务特殊要求】中的隐性成本(如包安装、质保期等)提示履约风险。"
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
            {"role": "system", "content": "你是一个极度犀利的电商风控专家与政企采购总监。擅长根据具体品类动态识破引流陷阱，防范多规格起步价作弊，并能在真实商品中挑选出性价比与销量最优的供应商。"},
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