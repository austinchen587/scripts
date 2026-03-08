import time
import json
import numpy as np
from config import BATCH_CONFIG
from data_filter import clean_and_filter_candidates
from llm_api import invoke_ollama
from config import OLLAMA_CONFIG
from logger import logger
from llm_api import invoke_ollama, analyze_image_with_vl # 确保把 analyze_image_with_vl 导进来

def get_gaussian_samples(items, n_samples=5):
    """
    基于正态分布(高斯分布)的抽样策略
    目标：选取能代表 95% 置信区间 (Mean ± 1.96σ) 的样本点
    """
    if not items: return []
    if len(items) <= n_samples:
        return items
        
    # 1. 提取价格
    prices = [x['price'] for x in items]
    
    # 2. 计算统计量
    mu = np.mean(prices)
    sigma = np.std(prices)
    
    # 3. 定义正态分布的关键锚点 (覆盖 95% CI)
    # [下界极值, 下界常用, 均值, 上界常用, 上界极值]
    # Z-scores: -1.96, -1.0, 0, +1.0, +1.96
    targets = [
        mu - 1.96 * sigma, # 对应 2.5% 分位
        mu - 1.0 * sigma,  # 对应 16% 分位
        mu,                # 对应 50% 分位
        mu + 1.0 * sigma,  # 对应 84% 分位
        mu + 1.96 * sigma  # 对应 97.5% 分位
    ]
    
    # 4. 寻找最接近的真实商品
    selected_indices = set()
    samples = []
    
    for t in targets:
        # 找到价格最接近 target 的商品索引
        closest_idx = min(range(len(prices)), key=lambda i: abs(prices[i] - t))
        
        # 避免重复 (除非数据量太少不够分)
        if closest_idx not in selected_indices:
            selected_indices.add(closest_idx)
            samples.append(items[closest_idx])
        else:
            # 如果撞车了(比如分布极窄)，尝试找旁边没选过的
            # 这里的简单处理是：如果已经选了，就跳过，最后补齐
            pass
            
    # 5. 如果样本不够5个(因为重复)，用均匀采样补齐
    if len(samples) < n_samples:
        remaining_count = n_samples - len(samples)
        # 从剩下的里面选
        remaining_indices = [i for i in range(len(items)) if i not in selected_indices]
        if remaining_indices:
            # 均匀切分剩余索引
            step = len(remaining_indices) / remaining_count
            for i in range(remaining_count):
                idx = remaining_indices[int(i * step)]
                samples.append(items[idx])
                
    # 6. 按价格排序输出，方便人类阅读
    samples.sort(key=lambda x: x['price'])
    return samples

def build_tier_selection_prompt(demand, tiers):
    """
    构建【价格段选择】Prompt - 修正版
    核心逻辑：先看规格是否匹配，再看价格。
    """
    summary = []
    for tier_name, items in tiers.items():
        if not items: continue
        
        # 使用高斯抽样获取代表性样本
        samples = get_gaussian_samples(items, 5)
        
        avg_p = sum(x['price'] for x in items) / len(items)
        
        # 构建样本描述
        sample_desc = []
        for x in samples:
            # 加入店铺名辅助判断（有些店铺名带"配件"）
            sample_desc.append(f"- [￥{x['price']}] {x['title'][:50]}")
            
        sample_text = "\n".join(sample_desc)
        
        summary.append({
            "tier": tier_name,
            "stat_info": f"均价 ￥{avg_p:.1f} (共{len(items)}家)",
            "gaussian_samples": sample_text
        })
        
    specs = demand.get('specifications')
    if not specs or str(specs).lower() == 'nan':
        specs = "无特殊硬性规格"

    # 关键修改：重写思考步骤，强制先做规格对齐
    return f"""
    我是采购员，需购买：【{demand.get('item_name')}】
    【硬性规格要求】：{specs}
    
    我按价格将市场商品分为了几组。请根据每组的【正态分布代表性样本】，判断哪个组**真正符合规格要求**。
    
    【分组详情】:
    {json.dumps(summary, ensure_ascii=False, indent=2)}
    
    【决策逻辑】(必须严格执行步骤 1)
    1. **规格对齐检验 (Spec Check)**：
       - 仔细阅读【需求规格】中的尺寸、容量、材质、型号等关键参数。
       - 逐一检查各组的【代表性样本】标题。
       - **淘汰**那些样本标题明显与需求规格不符的组。
       - *例如：需求要“大号/50cm”，如果“低价组”样本全是“小号/30cm”或“配件”，必须淘汰“低价组”！*
       - *例如：需求要“整箱”，如果某组样本是“单只体验装”，必须淘汰该组！*
    
    2. **选择最佳组**：
       - 在**符合规格**的组中，选择价格最低的组。
       - 如果“低价组”符合规格，首选“低价组”。
       - 如果“低价组”规格不符（如尺寸不对、仅为配件），则顺位检查“中价组”。
    
    请输出JSON:
    {{
        "spec_analysis": "分析需求关键参数是[X]。低价组样本显示为[Y]，是否匹配？中价组样本显示为[Z]...",
        "best_tier": "low / mid / high",
        "reason": "虽然低价组便宜，但其样本多为[X]与需求[Y]不符，因此选择规格匹配且价格合理的[Z]组..."
    }}
    """

def select_best_tier(demand, tiers):
    """调用LLM选择最佳价格段"""
    if len(tiers) == 1:
        return list(tiers.keys())[0]
        
    prompt = build_tier_selection_prompt(demand, tiers)
    res = invoke_ollama(prompt, "Tier_Selection")
    
    if res and 'best_tier' in res:
        chosen = res['best_tier'].lower()
        reason = res.get('reason', 'AI未提供理由')
        
        logger.info(f"🤖 AI 决策理由: {reason}")
        
        if 'low' in chosen: return 'low'
        if 'mid' in chosen: return 'mid'
        if 'high' in chosen: return 'high'
        
    if tiers.get('mid'): return 'mid'
    if tiers.get('low'): return 'low'
    return 'high'

def build_batch_prompt(demand, batch_candidates):
    """海选 Prompt"""
    simple_list = []
    for c in batch_candidates:
        simple_list.append({
            "id": c.get('sku'),
            "t": c.get('title', '')[:60],
            "p": c.get('price'),
            "s": c.get('sales'),
            "shop": c.get('shop_name', '')[:6]
        })

    specs = demand.get('specifications')
    if not specs or str(specs).lower() == 'nan':
        specs = "无特殊硬性规格，通用即可"

    return f"""
    我是采购员，需购买商品：【{demand.get('item_name')}】
    【硬性规格红线】：{specs}
    
    请帮我筛选 {BATCH_CONFIG['winners_per_batch']} 个晋级商品。
    
    【筛选逻辑】
    1. **一票否决**：仔细阅读商品标题(t)，凡是与【硬性规格】冲突的（如要求1.5匹却给3匹，要求纯棉却给涤纶），直接剔除！
    2. **性价比**：在符合规格的前提下，价格(p)越低越好，销量(s)越高越好。
    
    【候选列表】
    {json.dumps(simple_list, ensure_ascii=False)}
    
    请输出JSON（仅包含晋级者）:
    {{
        "winners": [
            {{
                "id": "SKU编号", 
                "match_check": "符合/基本符合",
                "reason": "简述理由"
            }}
        ]
    }}
    """

def build_final_prompt(demand, finalists):
    """决赛 Prompt"""
    simple_list = [{
        "sku": c.get('sku'),
        "title": c.get('title', ''), 
        "price": c.get('price'), 
        "sales": c.get('sales'),
        "shop": c.get('shop_name')
    } for c in finalists]
    
    specs = demand.get('specifications')
    if not specs or str(specs).lower() == 'nan':
        specs = "无特殊硬性规格"

    return f"""
    【终极决选】从这 {len(finalists)} 家优胜者中选出前 3 名。
    
    【采购目标】：{demand.get('item_name')}
    【规格要求】：{specs}
    
    【任务】请仔细对比“商品标题”与“规格要求”。
    
    【候选列表】
    {json.dumps(simple_list, ensure_ascii=False)}
    
    请严格输出JSON，必须包含 'match_evidence' (匹配证据):
    {{
        "selected": [
            {{
                "rank": 1, 
                "sku": "...", 
                "match_evidence": "需求要求[X]，商品标题包含[X]，参数一致",
                "reason": "价格优势明显..."
            }},
            ...
        ],
        "overall_reasoning": "总结"
    }}
    """

def call_ollama_batch(demand, batch_candidates, round_num, batch_idx):
    prompt = build_batch_prompt(demand, batch_candidates)
    desc = f"R{round_num}-B{batch_idx}"
    
    result = invoke_ollama(prompt, desc)
    time.sleep(BATCH_CONFIG['sleep_between_batches'])

    if result and 'winners' in result:
        winner_skus = set()
        for w in result['winners']:
            sku_id = None
            if isinstance(w, dict):
                sku_id = w.get('id') or w.get('sku')
                if w.get('match_check') == '不符合': continue
            elif isinstance(w, str):
                sku_id = w
            
            if sku_id: winner_skus.add(str(sku_id))
                
        valid_winners = [c for c in batch_candidates if str(c['sku']) in winner_skus]
        logger.info(f"  > [{desc}] 晋级: {len(valid_winners)}/{len(batch_candidates)}")
        if valid_winners: return valid_winners

    logger.warning(f"  > [{desc}] AI未返回有效结果或全被剔除，执行价格兜底。")
    return sorted(batch_candidates, key=lambda x: x['price'])[:BATCH_CONFIG['winners_per_batch']]

def tournament_selection(demand, candidates):
    # 1. 高级数据清洗（分层清洗）
    tiered_pool = clean_and_filter_candidates(candidates)
    
    if not tiered_pool:
        logger.warning("有效候选商品为0，流程终止。")
        return None
    
    # 2. 只有一组数据
    if 'default' in tiered_pool:
        current_pool = tiered_pool['default']
        logger.info(f"数据量少，不分层，共 {len(current_pool)} 家参与PK")
    else:
        # 3. 多组数据，让 AI 选一组
        best_tier_name = select_best_tier(demand, tiered_pool)
        current_pool = tiered_pool.get(best_tier_name, [])
        logger.info(f"AI 选择了价格段: [{best_tier_name}]，该组共 {len(current_pool)} 家参与后续PK")
        
        # 回退
        if not current_pool:
            logger.warning(f"AI 选择的 [{best_tier_name}] 组为空，执行自动回退。")
            best_tier_name = max(tiered_pool, key=lambda k: len(tiered_pool[k]))
            current_pool = tiered_pool[best_tier_name]
            logger.info(f"回退至数据最多的组: [{best_tier_name}] ({len(current_pool)}家)")

    # 4. 循环淘汰
    round_num = 1
    while len(current_pool) > BATCH_CONFIG['batch_size']:
        logger.info(f"--- 第 {round_num} 轮淘汰赛 (当前: {len(current_pool)}家) ---")
        next_pool = []
        batches = [current_pool[i:i+BATCH_CONFIG['batch_size']] for i in range(0, len(current_pool), BATCH_CONFIG['batch_size'])]
        
        for idx, batch in enumerate(batches):
            winners = call_ollama_batch(demand, batch, round_num, idx+1)
            next_pool.extend(winners)
            
        current_pool = next_pool
        round_num += 1
        if not current_pool: return None

    # ============================================================
    # 👉 [漏斗截断] 检查留下来的优胜者是否已经抓过详情了？
    # ============================================================
    all_ready = all(c.get('fetch_status', 0) == 2 for c in current_pool)
    if not all_ready:
        logger.info(f"⏸️ 发现 Top {len(current_pool)} 候选人尚未获取详情，中断 AI 决赛，挂起并呼叫爬虫...")
        return {
            "status": "need_detail", 
            "skus": [c['sku'] for c in current_pool]
        }
    # ============================================================

    logger.info(f"--- 终极决选 (剩余: {len(current_pool)}家) ---")

    # ============================================================
    # 👉 [升级版] 解析爬虫回传的 JSON，智能触发图文混合解析 (基于型号核查)
    # ============================================================
    # 提前把需求规格拆解成关键词列表 (例如: "NP-CR2300W 白色" -> ['NP-CR2300W', '白色'])
    target_specs = str(demand.get('specifications', ''))
    target_keywords = [k for k in target_specs.replace(';',' ').replace(',',' ').split() if len(k)>1]

    for c in current_pool:
        detail_json_str = c.get('detail_specs')
        c['final_specs_text'] = "无有效参数"
        
        if detail_json_str:
            try:
                specs_data = json.loads(detail_json_str)
                page_text = specs_data.get('text', '')
                img_path = specs_data.get('image_path', '')

                # 1. 检查文本是否缺失了我们要找的核心型号信息
                text_missing_key_info = False
                if target_keywords and page_text:
                    # 统计文本中命中了多少个需求关键词
                    match_count = sum(1 for k in target_keywords if k.upper() in page_text.upper())
                    # 如果连一个核心词（比如型号）都没在网页文本里找到，说明文本是废话/兜底文案！
                    if match_count == 0:
                        text_missing_key_info = True

                # 2. 【终极判断】：如果没有图、或者文本包含了“未提取到”、或者字数极少、或者【缺失核心型号】，全都要看图！
                if img_path and ("未提取到" in page_text or len(page_text) < 30 or text_missing_key_info):
                    logger.info(f"👁️ 发现 [{c['sku']}] 网页纯文本中未包含目标型号信息，正在召唤 Qwen3-VL 识图分析...")
                    vl_text = analyze_image_with_vl(img_path, demand.get('item_name'))
                    c['final_specs_text'] = f"{page_text}\n【Qwen3-VL 读图提取参数】:\n{vl_text}"
                    logger.info(f"   ✅ 图文解析完毕！")
                else:
                    c['final_specs_text'] = page_text # 文本里明确写了我们要的型号，直接用，不浪费算力
            except Exception as e:
                c['final_specs_text'] = str(detail_json_str)
    # ============================================================


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
                full_reason = f"【规格验证: {evidence}】 {ai_reason}"
                
                final_selected.append({
                    "rank": 0, "sku": sku, "shop": orig['shop_name'], 
                    "price": orig['price'], "platform": orig.get('platform',''),
                    "detail_url": orig['detail_url'], "reason": full_reason
                })

    # ============================================================
    # 👉 [修改] 删除了之前 while 凑数补位的逻辑，宁可返回空列表也不乱塞错误商品！
    # ============================================================
    final_selected.sort(key=lambda x: x['price'])
    for i, item in enumerate(final_selected): 
        item['rank'] = i + 1

    overall = llm_result.get('overall_reasoning', '') if isinstance(llm_result, dict) else ""
    return {"selected": final_selected, "overall_reasoning": overall}