# llm_service.py
import time
import json
import requests
from config import BATCH_CONFIG, API_KEY, API_SECRET
from data_filter import clean_and_filter_candidates
from llm_api import invoke_ollama, build_batch_prompt, build_final_prompt
from logger import logger
from db_manager import get_connection

def extract_specs_for_llm(detail_json):
    """【终极兼容版】自适应提取底层参数表"""
    if not detail_json or "item" not in detail_json: return "无详细规格数据"
    item = detail_json["item"]
    core_props = []
    
    # 策略 1: 淘宝 props
    raw_p = item.get("props")
    if isinstance(raw_p, list):
        for p in raw_p:
            if isinstance(p, dict) and "name" in p: core_props.append(f"{p['name']}: {p['value']}")
    
    # 策略 2: 京东 attributes/props_name
    raw_a = item.get("attributes")
    if isinstance(raw_a, list):
        for a in raw_a:
            if isinstance(a, str): core_props.append(a)
            elif isinstance(a, dict) and "name" in a: core_props.append(f"{a['name']}: {a['value']}")
    
    if not core_props:
        pn = item.get("props_name", "")
        if isinstance(pn, str) and pn:
            for part in pn.split(";"):
                sub = part.split(":")
                if len(sub) >= 4: core_props.append(f"{sub[-2]}: {sub[-1]}")
    
    core_props = list(dict.fromkeys(core_props))[:40]
    return json.dumps({
        "底层参数表": core_props if core_props else "未提取到结构化参数",
        "SKU列表": item.get("skus", {}).get("sku", [])[:5],
        "阶梯价": item.get("priceRange", [])
    }, ensure_ascii=False)

def run_initial_filter(demand, candidates):
    """【评分晋级制】取代随机抽样"""
    tiered_pool = clean_and_filter_candidates(candidates, demand)
    current_pool = tiered_pool.get('default', [])
    if not current_pool: return []

    round_num = 1
    while len(current_pool) > 5:
        logger.info(f"--- 🥊 第 {round_num} 轮 AI 初筛 (当前 {len(current_pool)} 家) ---")
        batches = [current_pool[i:i + BATCH_CONFIG['batch_size']] for i in range(0, len(current_pool), BATCH_CONFIG['batch_size'])]
        next_pool = []
        
        for idx, batch in enumerate(batches):
            llm_res = invoke_ollama(build_batch_prompt(demand, batch, round_num, idx), f"初筛_B{idx}")
            survs = None
            if llm_res:
                survs = llm_res.get('survivors') or llm_res.get('winners') or llm_res.get('selected_skus')
            
            if survs:
                w_ids = [str(x) if isinstance(x, (int, str)) else str(x.get('id', x.get('sku', ''))) for x in survs]
                next_pool.extend([c for c in batch if str(c['sku']) in w_ids])
            else:
                # 👉 AI 选不出，直接取本组评分最高的前 3 名
                logger.warning(f"   ⚠️ AI 罢工，根据评分自动晋级 Top 3")
                batch.sort(key=lambda x: (-x.get('score', 0), x['price']))
                next_pool.extend(batch[:3])
                
        if len(next_pool) >= len(current_pool):
            logger.warning("⚠️ 筛选效能降低，强制取评分最高的 5 家进入终选")
            current_pool.sort(key=lambda x: (-x.get('score', 0), x['price']))
            return current_pool[:5]
            
        current_pool = next_pool
        round_num += 1

    current_pool.sort(key=lambda x: (-x.get('score', 0), x['price']))
    return current_pool[:5]

def run_final_decision(demand, top_5_candidates, platform, pid, brand_id):
    """第四步：终极决选"""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            for c in top_5_candidates:
                num_iid = c.get('sku')
                cur.execute(f"SELECT raw_data FROM procurement_commodity_{platform}_detail WHERE brand_id = %s AND num_iid = %s ORDER BY id DESC LIMIT 1", (brand_id, str(num_iid)))
                row = cur.fetchone()
                if row and row[0]:
                    detail_json = row[0] if isinstance(row[0], dict) else json.loads(row[0])
                    c['final_specs_text'] = extract_specs_for_llm(detail_json)
                else:
                    c['final_specs_text'] = c.get('title', '缺漏详情数据')
    except Exception as e:
        logger.error(f"提取详情出错: {e}")
    finally:
        if conn: conn.close()

    logger.info("🏆 详情挂载完毕，开始最终裁决...")
    prompt_final = build_final_prompt(demand, top_5_candidates)
    llm_result = invoke_ollama(prompt_final, "Final_Decision")
    
    final_selected = []
    pool_map = {str(c['sku']): c for c in top_5_candidates}
    if llm_result and 'selected' in llm_result:
        for idx, item in enumerate(llm_result['selected'][:3]):
            sku = str(item.get('sku') or item.get('id') or "")
            if sku in pool_map:
                orig = pool_map[sku]
                final_selected.append({
                    "rank": idx + 1, "sku": sku, "shop": orig['shop_name'], 
                    "price": orig['price'], "platform": orig.get('platform',''),
                    "detail_url": orig['detail_url'], "reason": f"【规格核验: {item.get('match_evidence', '完成')}】 {item.get('reason', '')}"
                })
    return {"selected": final_selected, "overall_reasoning": llm_result.get('overall_reasoning', '') if llm_result else ""}