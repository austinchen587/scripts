import time
import json
import numpy as np
import concurrent.futures
from config import BATCH_CONFIG
from data_filter import clean_and_filter_candidates
# 👉 【核心修复】直接从 llm_api 导入统一的 Prompt 构建器
from llm_api import invoke_ollama, build_tier_selection_prompt, build_batch_prompt, build_final_prompt
from config import OLLAMA_CONFIG
from logger import logger

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

    logger.warning(f"  > [{desc}] AI未返回有效结果或全被剔除，执行价格兜底。")
    return sorted(batch_candidates, key=lambda x: x['price'])[:BATCH_CONFIG['winners_per_batch']]

def tournament_selection(demand, candidates):
    tiered_pool = clean_and_filter_candidates(candidates, demand)
    if not tiered_pool:
        logger.warning("有效候选商品为0，流程终止。")
        return None
    
    if 'default' in tiered_pool:
        current_pool = tiered_pool['default']
        logger.info(f"数据量少，不分层，共 {len(current_pool)} 家参与PK")
    else:
        best_tier_name = select_best_tier(demand, tiered_pool)
        if best_tier_name == 'none':
            return {
                "selected": [], 
                "overall_reasoning": "系统判定：所有候选价格组内的代表性商品，均不符合您的核心参数要求（如尺寸、规格等），存在严重货不对板风险，建议修改采购词重新寻源。"
            }
            
        current_pool = tiered_pool.get(best_tier_name, [])
        logger.info(f"AI 选择了价格段: [{best_tier_name}]，该组共 {len(current_pool)} 家参与后续PK")
        
        if not current_pool:
            logger.warning(f"AI 选择的 [{best_tier_name}] 组为空，执行自动回退。")
            best_tier_name = max(tiered_pool, key=lambda k: len(tiered_pool[k]))
            current_pool = tiered_pool[best_tier_name]
            logger.info(f"回退至数据最多的组: [{best_tier_name}] ({len(current_pool)}家)")

    round_num = 1
    while len(current_pool) > BATCH_CONFIG['batch_size']:
        logger.info(f"--- 第 {round_num} 轮淘汰赛 (当前: {len(current_pool)}家) ---")
        next_pool = []
        batches = [current_pool[i:i+BATCH_CONFIG['batch_size']] for i in range(0, len(current_pool), BATCH_CONFIG['batch_size'])]
        
        # 👉 [全新并发提速]：同时向阿里云发送多个批次请求！
        # 设置最大线程数为批次数量，或者最大不超过 5 (防止触发云端 QPS 限流)
        max_workers = min(len(batches), 5) 
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_batch = {}
            for idx, batch in enumerate(batches):
                # 每发一个请求，主线程稍微休眠 0.2 秒，防止瞬间 QPS 爆炸触发云端拦截
                time.sleep(0.2) 
                future = executor.submit(call_ollama_batch, demand, batch, round_num, idx+1)
                future_to_batch[future] = batch
            
            # 等待它们并发完成，谁先完成就先收集谁的胜出者
            for future in concurrent.futures.as_completed(future_to_batch):
                try:
                    winners = future.result()
                    if winners:
                        next_pool.extend(winners)
                except Exception as exc:
                    logger.error(f"批次并发处理时发生崩溃: {exc}")
            
        # 👉 【核心修复】：死循环熔断器
        # 如果一轮比赛打完，晋级的人数居然大于等于参赛人数（大模型全部放行）
        if len(next_pool) >= len(current_pool):
            logger.warning(f"🚨 淘汰赛陷入停滞 (本轮剩余 {len(next_pool)} 家未减少)，强制熔断，直接截取高分送入决选！")
            # 按 Python 洗好的分数(优先)和价格(其次)排序，强行只保留一个批次的人数（默认10人）送进决选
            next_pool.sort(key=lambda x: (-x.get('score', 0), x['price']))
            current_pool = next_pool[:BATCH_CONFIG['batch_size']]
            break # 打破死循环

        current_pool = next_pool
        round_num += 1
        if not current_pool: return None

    logger.info(f"--- 终极决选 (剩余: {len(current_pool)}家) ---")

    target_specs = str(demand.get('specifications', ''))
    target_keywords = [k for k in target_specs.replace(';',' ').replace(',',' ').split() if len(k)>1]

    for c in current_pool:
        c['final_specs_text'] = c.get('title', '未知标题')

    prompt_final = build_final_prompt(demand, current_pool)
    llm_result = invoke_ollama(prompt_final, "Final_Decision")
    
    final_selected = []
    pool_map = {str(c['sku']): c for c in current_pool}
    
    if llm_result and 'selected' in llm_result:
        for item in llm_result['selected']:
            sku = None
            if isinstance(item, dict):
                sku = str(item.get('sku') or item.get('id'))
            
            if sku and sku in pool_map:
                orig = pool_map[sku]
                evidence = item.get('match_evidence', '无详细比对') if isinstance(item, dict) else 'AI未提供详情'
                ai_reason = item.get('reason', '') if isinstance(item, dict) else ''
                full_reason = f"【品牌与规格核验: {evidence}】 {ai_reason}"
                
                final_selected.append({
                    "rank": 0, "sku": sku, "shop": orig['shop_name'], 
                    "price": orig['price'], "platform": orig.get('platform',''),
                    "detail_url": orig['detail_url'], "reason": full_reason
                })

    final_selected.sort(key=lambda x: x['price'])
    for i, item in enumerate(final_selected): 
        item['rank'] = i + 1

    overall = llm_result.get('overall_reasoning', '') if isinstance(llm_result, dict) else ""
    return {"selected": final_selected, "overall_reasoning": overall}