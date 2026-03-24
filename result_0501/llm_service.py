import time
import json
import numpy as np
from config import BATCH_CONFIG, API_KEY, API_SECRET # 引入 API 配置
from data_filter import clean_and_filter_candidates
# 👉 【核心修复】直接从 llm_api 导入统一的 Prompt 构建器
from llm_api import invoke_ollama, build_tier_selection_prompt, build_batch_prompt, build_final_prompt
from config import OLLAMA_CONFIG
from logger import logger
import concurrent.futures  # 👉 [新增] 引入多线程并发库
from db_manager import save_detail_raw_data # 引入入库方法
import requests
from db_manager import get_connection

def fetch_detail_from_api(plat, num_iid):
    """调用 API 获取商品详情"""
    url = f"https://api-gw.onebound.cn/{plat}/item_get/"
    try:
        res = requests.get(url, params={"key": API_KEY, "secret": API_SECRET, "num_iid": num_iid}, timeout=15)
        return res.json()
    except Exception as e:
        logger.error(f"❌ 详情 API 请求失败 [{num_iid}]: {e}")
        return None

def extract_specs_for_llm(detail_json):
    """
    【终极兼容版】自适应提取淘宝、京东、1688 的底层规格
    防止平台字段差异导致 AI 漏看关键参数
    """
    if not detail_json or "item" not in detail_json: 
        return "无详细规格数据"
        
    item = detail_json["item"]
    core_props = []

    # ==========================================
    # 策略 1：淘宝/天猫 标准格式 (props 数组)
    # ==========================================
    raw_props = item.get("props")
    if isinstance(raw_props, list):
        for p in raw_props:
            if isinstance(p, dict) and "name" in p and "value" in p:
                core_props.append(f"{p['name']}: {p['value']}")

    # ==========================================
    # 策略 2：京东/部分其他平台 (attributes 字段)
    # ==========================================
    raw_attrs = item.get("attributes")
    if isinstance(raw_attrs, list):
        for a in raw_attrs:
            if isinstance(a, str):
                core_props.append(a)
            elif isinstance(a, dict) and "name" in a and "value" in a:
                core_props.append(f"{a['name']}: {a['value']}")
    elif isinstance(raw_attrs, dict):
        for k, v in raw_attrs.items():
            core_props.append(f"{k}: {v}")

    # ==========================================
    # 策略 3：京东特色 SKU 级参数兜底 (props_name)
    # ==========================================
    if not core_props:
        props_name = item.get("props_name", "")
        if isinstance(props_name, str) and props_name:
            # 解析京东常见的 "1:1:颜色:黑色;2:2:处理器:i5" 格式
            parts = props_name.split(";")
            for part in parts:
                sub_parts = part.split(":")
                if len(sub_parts) >= 4:  # 提取后两位，即 "颜色: 黑色"
                    core_props.append(f"{sub_parts[-2]}: {sub_parts[-1]}")
                elif len(sub_parts) == 2:
                    core_props.append(f"{sub_parts[0]}: {sub_parts[1]}")

    # ==========================================
    # 数据清洗与 Token 保护
    # ==========================================
    # 去重（保持顺序）
    core_props = list(dict.fromkeys(core_props))
    # 截断（防止某些数码产品参数多达上百条，撑爆大模型 Token，取前 40 条核心参数）
    core_props = core_props[:40]

    specs = {
        "底层核心参数表": core_props if core_props else "未提取到结构化参数，请重点参考可选SKU",
        "可选SKU列表": item.get("skus", {}).get("sku", [])[:5],  # 截取前 5 个防超限
        "阶梯价格": item.get("priceRange", []) # 兼容 1688 特色
    }
    
    return json.dumps(specs, ensure_ascii=False)




def get_gaussian_samples(items, n_samples=5):
    """基于正态分布的抽样策略"""
    if not items: return []
    if len(items) <= n_samples: return items
    prices = [x['price'] for x in items]
    mu, sigma = np.mean(prices), np.std(prices)
    targets = [mu - 1.96*sigma, mu - 1.0*sigma, mu, mu + 1.0*sigma, mu + 1.96*sigma]
    selected_indices = set()
    samples = []
    for t in targets:
        closest_idx = min(range(len(prices)), key=lambda i: abs(prices[i] - t))
        if closest_idx not in selected_indices:
            selected_indices.add(closest_idx)
            samples.append(items[closest_idx])
    if len(samples) < n_samples:
        remaining_indices = [i for i in range(len(items)) if i not in selected_indices]
        if remaining_indices:
            step = len(remaining_indices) / (n_samples - len(samples))
            for i in range(n_samples - len(samples)):
                samples.append(items[remaining_indices[int(i * step)]])
    samples.sort(key=lambda x: x['price'])
    return samples

def select_best_tier(demand, tiered_pool):
    """让 AI 选择最合适的价格组"""
    samples = {}
    for tier, items in tiered_pool.items():
        samples[tier] = get_gaussian_samples(items)
        
    prompt = build_tier_selection_prompt(demand, samples)
    res = invoke_ollama(prompt, "Select_Tier")
    
    if res and 'selected_tier' in res and res['selected_tier'] in tiered_pool:
        logger.info(f"🧠 AI 物价估算: {res.get('market_price_estimate', '')}")
        logger.info(f"🕵️‍♂️ AI 排雷分析: {res.get('tier_analysis', '')}")
        logger.info(f"🤖 AI 最终决策: {res.get('reason')}")
        return res['selected_tier']
    
    logger.warning("AI 分层选择失败或格式错误，默认选择 mid 组")
    return 'mid' if 'mid' in tiered_pool else list(tiered_pool.keys())[0]

def call_ollama_batch(demand, batch_candidates, round_num, batch_idx):
    prompt = build_batch_prompt(demand, batch_candidates, round_num, batch_idx)
    desc = f"R{round_num}-B{batch_idx}"
    
    result = invoke_ollama(prompt, desc)
    time.sleep(BATCH_CONFIG['sleep_between_batches'])

    if result:
        # 👉 【核心修复】兼容大模型输出的 survivors 或 winners
        survivor_list = result.get('survivors') or result.get('winners')
        
        if survivor_list is not None:
            winner_skus = set()
            for w in survivor_list:
                if isinstance(w, dict):
                    if w.get('match_check') in ['不符合', '淘汰']: continue
                    sku_id = w.get('id') or w.get('sku')
                elif isinstance(w, (str, int)):
                    sku_id = str(w)
                else:
                    continue
                    
                if sku_id: winner_skus.add(str(sku_id))
                    
            valid_winners = [c for c in batch_candidates if str(c['sku']) in winner_skus]
            logger.info(f"  > [{desc}] 晋级: {len(valid_winners)}/{len(batch_candidates)}")
            
            if valid_winners: 
                # 👉 【核心修复1】：不管大模型放行多少个，强制按分数和价格优选，并强行截断！防止死循环！
                valid_winners.sort(key=lambda x: (-x.get('score', 0), x['price']))
                return valid_winners[:BATCH_CONFIG['winners_per_batch']]
            else: 
                logger.warning(f"  > [{desc}] AI 返回了空列表，无人晋级。")
        else:
            logger.warning(f"  > [{desc}] AI 的 JSON 中没有 survivors 字段。")

    logger.warning(f"  > [{desc}] AI未返回有效结果或全被剔除，执行价格兜底。")
    return sorted(batch_candidates, key=lambda x: x['price'])[:BATCH_CONFIG['winners_per_batch']]

def tournament_selection(demand, candidates, platform, pid, brand_id):
    """
    👉 [架构优化版] 多轮初筛 (Title) -> Top 5 抓详情入库 -> 终选前 3
    """
    # 1. 规则硬筛选
    tiered_pool = clean_and_filter_candidates(candidates, demand)
    current_pool = tiered_pool.get('default', [])
    if not current_pool:
        logger.warning("有效候选商品为0，流程终止。")
        return None

    # 2. 多轮 AI 初筛打擂台 (基于 Title)
    round_num = 1
    # 核心：保留多轮筛选，只要数量大于 5 就继续淘汰
    while len(current_pool) > 5:
        logger.info(f"--- 🥊 第 {round_num} 轮初筛开始: 当前剩余 {len(current_pool)} 家 ---")
        
        # 将大池子拆分为每批 15 个的擂台
        batches = [current_pool[i:i + BATCH_CONFIG['batch_size']] for i in range(0, len(current_pool), BATCH_CONFIG['batch_size'])]
        next_pool = []
        
        for idx, batch in enumerate(batches):
            prompt = build_batch_prompt(demand, batch)
            llm_result = invoke_ollama(prompt, f"初筛_Round{round_num}_Batch{idx}")
            
            if llm_result and 'selected_skus' in llm_result:
                winners = [c for c in batch if str(c['sku']) in [str(x) for x in llm_result['selected_skus']]]
                next_pool.extend(winners)
            else:
                # 兜底抽样
                next_pool.extend(get_gaussian_samples(batch, n_samples=3))
                
        # 防死循环：如果 AI 没有淘汰掉任何一家，强制高斯抽样截断
        if len(next_pool) >= len(current_pool):
            logger.warning("⚠️ AI 未能有效缩小范围，触发强制高斯截断。")
            current_pool = get_gaussian_samples(current_pool, 5)
            break
            
        current_pool = next_pool
        round_num += 1

    # ==========================================
    # 3. 详情获取与入库 (此时 current_pool 最多 5 家)
    # ==========================================
    top_5_candidates = current_pool[:5] # 兜底强制截断不超过 5 家
    logger.info(f"🎯 标题初筛结束，锁定 Top {len(top_5_candidates)} 家，准备抓取详情...")

    for c in top_5_candidates:
        num_iid = c.get('sku') or c.get('num_iid')
        logger.info(f"  > 抓取详情 [{platform}] ID: {num_iid}")
        
        detail_json = fetch_detail_from_api(platform, num_iid)
        
        if detail_json and detail_json.get("error_code") == "0000":
            # A. 存入云端 Detail 表
            save_detail_raw_data(pid, brand_id, num_iid, platform, detail_json)
            # B. 提取规格挂载到候选人身上，供下一步 Final 决策使用
            c['final_specs_text'] = extract_specs_for_llm(detail_json)
        else:
            c['final_specs_text'] = c.get('title', '未知标题') # 抓取失败时的兜底


    # ==========================================
    # 4. 终极决选 (基于包含详细规格的 Top 5)
    # ==========================================
    logger.info("🏆 进入终选环节，生成前 3 名推荐...")
    prompt_final = build_final_prompt(demand, top_5_candidates)
    llm_result = invoke_ollama(prompt_final, "Final_Decision")
    
    final_selected = []
    pool_map = {str(c['sku']): c for c in top_5_candidates}
    
    if llm_result and 'selected' in llm_result:
        # 只取 AI 返回的前 3 家，并自动分配 1, 2, 3 名次
        for idx, item in enumerate(llm_result['selected'][:3]):
            sku = str(item.get('sku') or item.get('id') or "")
            if sku in pool_map:
                orig = pool_map[sku]
                evidence = item.get('match_evidence', '无详细比对')
                ai_reason = item.get('reason', '')
                full_reason = f"【品牌与规格核验: {evidence}】 {ai_reason}"
                
                final_selected.append({
                    "rank": idx + 1, # 👉 修复：动态赋排名 1, 2, 3
                    "sku": sku, "shop": orig['shop_name'], 
                    "price": orig['price'], "platform": orig.get('platform',''),
                    "detail_url": orig['detail_url'], "reason": full_reason
                })

    # 👉 修复：返回字典，既包含前三名列表，也包含财务风险告警结论，方便 main.py 接收
    return {
        "selected": final_selected,
        "overall_reasoning": llm_result.get('overall_reasoning', '') if llm_result else ""
    }


def run_initial_filter(demand, candidates):
    """【第二棒：初筛】清洗和大名单多轮淘汰 -> Top 5"""
    tiered_pool = clean_and_filter_candidates(candidates, demand)
    current_pool = tiered_pool.get('default', [])
    if not current_pool: return []

    round_num = 1
    while len(current_pool) > 5:
        logger.info(f"--- 🥊 第 {round_num} 轮初筛开始: 当前剩余 {len(current_pool)} 家 ---")
        batches = [current_pool[i:i + BATCH_CONFIG['batch_size']] for i in range(0, len(current_pool), BATCH_CONFIG['batch_size'])]
        next_pool = []
        
        for idx, batch in enumerate(batches):
            prompt = build_batch_prompt(demand, batch, round_num, idx)
            llm_result = invoke_ollama(prompt, f"初筛_Round{round_num}_Batch{idx}")
            
            # ---------------------------------------------------------
            # 🔥 核心优化 3：极度鲁棒的 JSON 解析，防止漏接大模型的单
            # ---------------------------------------------------------
            survs = None
            if llm_result:
                # 暴力兼容各种可能的键名
                survs = llm_result.get('survivors') or llm_result.get('winners') or llm_result.get('selected_skus') or llm_result.get('selected')

            if survs is not None:
                w_ids = []
                for x in survs:
                    # 兼容 LLM 输出纯字符串数组，或输出对象数组的情况
                    if isinstance(x, (int, str)):
                        w_ids.append(str(x))
                    elif isinstance(x, dict):
                        w_ids.append(str(x.get('id', x.get('sku', ''))))
                        
                winners = [c for c in batch if str(c['sku']) in w_ids]
                next_pool.extend(winners)
            else:
                logger.warning(f"   ⚠️ 第 {round_num} 轮 Batch {idx} 发生 AI 罢工，局部高斯截断。")
                next_pool.extend(get_gaussian_samples(batch, n_samples=3))
                
        if len(next_pool) >= len(current_pool):
            logger.warning("⚠️ AI 未能有效缩小范围，触发强制高斯截断。")
            current_pool = get_gaussian_samples(current_pool, 5)
            break
            
        current_pool = next_pool
        round_num += 1

    return current_pool[:5]

def run_final_decision(demand, top_5_candidates, platform, pid, brand_id):
    """【第四棒：终选】自己去数据库把爬虫刚存进去的 JSONB 拉出来喂给模型"""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            for c in top_5_candidates:
                num_iid = c.get('sku') or c.get('num_iid')
                table_detail = f"procurement_commodity_{platform}_detail"
                
                # 去数据库查刚刚 api_worker 存进来的详情 JSONB
                cur.execute(f"""
                    SELECT raw_data FROM {table_detail} 
                    WHERE brand_id = %s AND num_iid = %s 
                    ORDER BY id DESC LIMIT 1
                """, (brand_id, str(num_iid)))
                row = cur.fetchone()
                
                if row and row[0]:
                    detail_json = row[0] if isinstance(row[0], dict) else json.loads(row[0])
                    c['final_specs_text'] = extract_specs_for_llm(detail_json)
                else:
                    c['final_specs_text'] = c.get('title', '未知标题')
    except Exception as e:
        logger.error(f"提取详情 JSONB 发生错误: {e}")
    finally:
        if conn: conn.close()

    # 进入终选
    logger.info("🏆 所有详情挂载完毕，生成前 3 名推荐...")
    prompt_final = build_final_prompt(demand, top_5_candidates)
    llm_result = invoke_ollama(prompt_final, "Final_Decision")
    
    final_selected = []
    pool_map = {str(c['sku']): c for c in top_5_candidates}
    
    if llm_result and 'selected' in llm_result:
        for idx, item in enumerate(llm_result['selected'][:3]):
            sku = str(item.get('sku') or item.get('id') or "")
            if sku in pool_map:
                orig = pool_map[sku]
                evidence = item.get('match_evidence', '无详细比对')
                ai_reason = item.get('reason', '')
                full_reason = f"【品牌与规格核验: {evidence}】 {ai_reason}"
                
                final_selected.append({
                    "rank": idx + 1, 
                    "sku": sku, "shop": orig['shop_name'], 
                    "price": orig['price'], "platform": orig.get('platform',''),
                    "detail_url": orig['detail_url'], "reason": full_reason
                })

    return {
        "selected": final_selected,
        "overall_reasoning": llm_result.get('overall_reasoning', '') if llm_result else ""
    }