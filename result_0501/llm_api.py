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
    """【宽进严出版】海选：只抓作弊，不纠细节"""
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
    【海选初审】第 {round_num} 轮，第 {batch_idx} 批次
    【采购大类】{demand.get('item_name')}
    【主要品牌】{brand_req}
    
    【🚨 海选核心任务：只抓作弊，宽容匹配】：
    你的任务是清理明显的垃圾数据，让基本符合【采购大类】的商品晋级。不要在这里死抠细微的颜色、内存或次要型号！
    
    1. 斩杀“挂羊头卖狗肉”：如果我们要买“整机/正品”，标题带有“支架/配件/套壳/贴膜/定金/尾款”的低价引流SKU，必须淘汰！
    2. 斩杀“低配引流高配”：如果标题罗列了多个规格（如“标配/高配”、“XX起”），请研判当前价格是否仅够买最低配且最低配毫无用处，如果是，直接淘汰。
    3. ⚠️【宽进原则】（最重要）：只要标题看起来属于我们要买的【采购大类】（例如我们要买平板，候选也是个正常的平板；我们要买钥匙柜，候选也是个正常的钥匙柜），且价格符合常理，就必须允许其晋级(survivors)！
    4. 品牌宽容：在海选阶段，即使品牌不完全匹配，只要商品属于同一个品类，也请暂时放行，由后续环节做最终比对。
    
    候选列表：
    {json.dumps(simple_list, ensure_ascii=False)}

    请严格输出 JSON 格式：
    {{
        "analysis": "只分析淘汰掉的商品原因，对放行的商品不用解释",
        "survivors": ["sku1", "sku2", "sku3"] // 只要不是恶意引流或跨界垃圾，尽量多放行！
    }}
    """

def build_final_prompt(demand, finalists):
    """【通用终极决选版】引入强制思维链（CoT），适用于全品类政企采购"""
    simple_list = []
    for c in finalists:
        item_data = {k: v for k, v in c.items() if k in ['sku', 'title', 'price', 'shop_name', 'sales']}
        if 'score' in c:
            item_data['score'] = c['score']  # 传递 Python 硬匹配的权重分
        simple_list.append(item_data)
        
    # 直接调用文件内已有的函数，不需要 import
    brand_req = _get_brand(demand)
    budget, business_reqs = _extract_budget_and_reqs(demand)
    
    qty = float(demand.get('quantity', demand.get('采购数量', 1)))
    budget_str = f"甲方该项目的总控制预算为：{budget}元" if budget > 0 else "无明确项目总控制预算"

    return f"""
    【终极决选法庭】请从以下经过程序初筛的幸存者中，严格按政企采购合规标准选出最完美的 3 家供应商。
    
    【采购需求核心数据】
    - 采购物品：{demand.get('item_name', '未提供')}
    - 🎯 指定品牌：{brand_req}  (⚠️极其重要红线：如非“无明确要求”，必须严格对齐该品牌，严禁推荐竞品！)
    - ⚙️ 核心规格：{demand.get('specifications', '无')}
    - 采购数量：{qty}
    - 商务要求：{business_reqs}
    - 财务控制：{budget_str}
    
    【🏆 通用选品终极法则与排雷红线】：
    1. 品牌合规一票否决：必须首先检查候选商品标题/店铺是否与【指定品牌】一致！如果明确指定了品牌，绝不允许自作主张推荐其他品牌的“平替”或“高性价比替代品”！
    2. 规格精准对应：仔细比对标题里的容量、尺寸、型号等核心参数，必须与【核心规格】完全一致。政企采购讲究“参数符合性定标”，严禁以“高配兼容”或“规格更大”为由偏离原始需求。
    3. 警惕“多规格起步价”：如果商品标题罗列了多个规格（如“标配/高配”、“XX型号起”），且当前标价极其便宜，必须判定该价格只够买其最低配置！若最低配置达不到我们的【核心规格】，直接判定为不匹配/作弊！
    4. 终极优选权重：在【品牌+规格完全匹配】的前提下，价格越低越好（为采购方释放利润空间），其次考虑销量和店铺资质（如旗舰店、专卖店优先）。
    
    【候选商品列表】(已由前置算法打分排序，score分数越高代表系统判定的文本匹配度越高)
    {json.dumps(simple_list, ensure_ascii=False)}
    
    【⚠️ 强制输出格式】
    请严格按以下 JSON 格式输出，你必须先执行 `verification_process` 逐一核验每个商品，再得出 `selected` 排名：
    {{
        "verification_process": [
            {{
                "sku": "...",
                "title_short": "简短标题",
                "brand_match": "是/否/无要求 (明确指出实际品牌是否与指定品牌相符)",
                "spec_match": "是/否/存疑 (规格参数是否完全达标)",
                "is_bait_price": "是/否 (是否存在多规格起步价引流作弊)",
                "conclusion": "合格/淘汰/备选"
            }}
        ],
        "selected": [
            {{
                "rank": 1, 
                "sku": "...", 
                "match_evidence": "详细说明为何该商品品牌匹配、规格达标且性价比最高", 
                "reason": "综合推荐理由..."
            }},
            {{"rank": 2, "sku": "...", "match_evidence": "...", "reason": "..."}},
            {{"rank": 3, "sku": "...", "match_evidence": "...", "reason": "..."}}
        ],
        "overall_reasoning": "请详细总结本次决选的整体评判逻辑和淘汰其他商品的原因"
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