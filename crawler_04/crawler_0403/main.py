# main.py
import time
import json
import random
from concurrent.futures import ThreadPoolExecutor, wait, FIRST_COMPLETED
from browser_manager import pool 
from engines.jd_engine import JDEngine
from engines.s1688_engine import S1688Engine
from engines.taobao_engine import TaobaoEngine
from processor import process_and_map
from logger_helper import logger
from db_helper import save_skus_to_db, save_task_result, clear_retry_placeholder, check_global_cache, r_client
from engines.base_engine import AntiSpiderException


# ================= 配置区域 =================
WORK_DURATION = 4 * 60 * 60 
REST_DURATION = 30 * 60
MAX_WORKERS = 1
NO_DATA_SYNC_INTERVAL = 2 * 60 

PLATFORM_COOLDOWN = {
    '京东': 0,
    '1688': 0,
    '淘宝': 0
}
COOLDOWN_TIME = 20 * 60  
# ===========================================

PROCESSING_BRAND_IDS = set()

def get_or_create_tab(browser, url_keyword, full_url):
    """智能复用标签页"""
    target_tab = None
    try:
        try: tab_ids = browser.tab_ids
        except: tab_ids = getattr(browser, '_tab_ids', [])
        
        for t_id in tab_ids:
            try:
                tab = browser.get_tab(t_id)
                if not tab: continue
                if url_keyword in (tab.url or ""):
                    target_tab = tab
                    break
            except: continue
        
        if target_tab:
            try: 
                if hasattr(browser.set, 'tab'): browser.set.tab(target_tab)
                else: target_tab.activate()
            except: pass 
        else:
            browser.new_tab(full_url)
    except Exception as e:
        logger.error(f"   ❌ 操作标签页失败: {e}")

def prepare_login_environment():
    """预热逻辑"""
    logger.info("="*60)
    logger.info("🔓 [系统启动] 正在唤醒所有专属浏览器...")
    if '京东' in pool.browsers:
        get_or_create_tab(pool.browsers['京东'], 'jd.com', 'https://www.jd.com/')
    if '淘宝' in pool.browsers:
        get_or_create_tab(pool.browsers['淘宝'], 'taobao.com', 'https://www.taobao.com/')
    if '1688' in pool.browsers:
        get_or_create_tab(pool.browsers['1688'], '1688.com', 'https://www.1688.com/')

    logger.info("🛑 [静默等待模式] 请在弹出的3个专属窗口登录，并搜索任意词...")
    while True:
        all_ready, not_ready_names = pool.check_all_browsers_ready()
        if all_ready:
            logger.info("✅ 所有浏览器就绪！")
            break
        time.sleep(2)
    logger.info("⏳ 倒计时 10秒 开跑...")
    time.sleep(10)

def process_whole_task(task):
    kw = task['key_word']
    pid = task['procurement_id']
    item_name = task['item_name']
    brand_id = task.get('brand_id')
    
    target_str = task.get('search_platform', '') or ''
    target_str = target_str.strip()

    logger.info(f"🔥 [领单] 开始处理: {item_name} (ID: {brand_id})")

    all_platforms = [
        ('京东', JDEngine),
        ('1688', S1688Engine),
        ('淘宝', TaobaoEngine)
    ]
    
    platforms_to_search = []
    if target_str:
        for p_name, p_class in all_platforms:
            if p_name in target_str:
                platforms_to_search.append((p_name, p_class))
        if platforms_to_search:
            logger.info(f"🎯 [目标平台] 系统指定: {[p[0] for p in platforms_to_search]}")
        else:
            chosen_platform = random.choice(all_platforms)
            platforms_to_search.append(chosen_platform)
            logger.info(f"🎯 [目标平台] 指定平台无效，随机单选兜底: {chosen_platform[0]}")
    else:
        chosen_platform = random.choice(all_platforms)
        platforms_to_search.append(chosen_platform)
        logger.info(f"🎯 [目标平台] 无推荐，随机单选: {chosen_platform[0]}")

    has_any_result = False
    skipped_due_to_cooldown = False 

    try:
        for platform_name, EngineClass in platforms_to_search:
            current_time = time.time()
            if PLATFORM_COOLDOWN.get(platform_name, 0) > current_time:
                remain_time = int(PLATFORM_COOLDOWN[platform_name] - current_time)
                logger.warning(f"⏳ [熔断保护] {platform_name} 正在冷却中 (剩余 {remain_time} 秒)，直接跳过搜索！")
                skipped_due_to_cooldown = True
                continue
                
            browser = pool.browsers.get(platform_name)
            if not browser:
                logger.error(f"⚠️ [系统异常] 未找到 {platform_name} 的专属浏览器，跳过！")
                continue

            b_name = getattr(browser, '_custom_name', platform_name)
            time.sleep(random.uniform(1.5, 3))
            logger.info(f"   👉 使用专属通道: [{b_name}] -> 搜索 {kw}")
            
            try:
                initial_tab_ids = browser.tab_ids
            except:
                initial_tab_ids = getattr(browser, '_tab_ids', [])
            
            try:
                engine = EngineClass(browser)
                raw_data = engine.search(kw)
                
                if raw_data:
                    logger.info(f"      ✅ [{b_name}] 抓取 {len(raw_data)} 条")
                    clean_records = process_and_map(raw_data, pid, item_name)
                    for r in clean_records:
                        r['brand_id'] = brand_id
                    save_skus_to_db(clean_records)
                    has_any_result = True
                else:
                    logger.info(f"      ⭕ [{b_name}] 未抓取到数据")

            except AntiSpiderException as e:
                    logger.error(f"🕸️ {e}")
                    # 触发验证码后，进行避险处理
                    logger.info(f"   -> 🔄 正在为 {plat} 执行避险重置 (跳转百度脱离险境)...")
                    try:
                        # 👉 [核心修复] 强行征用当前出事的标签页，直接飞去百度
                        if hasattr(engine, 'tab') and engine.tab:
                            engine.tab.get('https://www.baidu.com')
                            time.sleep(2)
                    except Exception as reset_e:
                        logger.error(f"   -> ❌ 避险跳转失败: {reset_e}")
                        pass
                    
                    PLATFORM_COOLDOWN[plat] = time.time() + COOLDOWN_TIME
                    logger.warning(f"   -> ⏱️ {plat} 已进入冷静期 {COOLDOWN_TIME/60} 分钟，本轮跳过该平台。")
                    continue

            except Exception as e:
                logger.error(f"      💥 [{b_name}] 抓取过程出错: {e}")
                
            finally:
                try:
                    try:
                        current_tab_ids = browser.tab_ids
                    except:
                        current_tab_ids = getattr(browser, '_tab_ids', [])

                    for t_id in current_tab_ids:
                        if t_id not in initial_tab_ids:
                            try:
                                logger.info(f"   🧹 [{b_name}] 清理残留的详情页/新窗口...")
                                tab_to_close = browser.get_tab(t_id)
                                if tab_to_close:
                                    tab_to_close.close()
                            except: pass
                    
                    if initial_tab_ids:
                        try:
                            target_tab = browser.get_tab(initial_tab_ids[-1])
                            if target_tab:
                                if hasattr(browser.set, 'tab'): browser.set.tab(target_tab)
                                else: target_tab.activate()
                        except: pass
                except Exception as cleanup_err:
                    logger.error(f"      💥 [{b_name}] 清理标签页出错: {cleanup_err}")

        # ==========================================
        # 👉 [修复 2] 结果结算与上报 (核心修复区)
        # ==========================================

        if has_any_result:
            # 抓取成功，必须写入 completed 状态，否则前端会一直转圈
            save_task_result(task, status='completed') 
            # 通知 AI 节点选品，带上发起请求的服务器 IP
            clear_retry_placeholder(brand_id, task.get('server_ip')) 
            
        elif task.get('status') == 'retry':
            pass # 已经在上面的 except 里保存过了
            
        elif skipped_due_to_cooldown:
            logger.info(f"🔄 任务 [{item_name}] 因目标平台全在冷却中，主动挂起重试。")
            save_task_result(task, status='retry') # 👉 挂起重试
            
        else:
            logger.warning(f"🚫 任务 [{item_name}] 无结果，标记人工审核。")
            save_task_result(task, status='failed') # 👉 无结果
        
        logger.info(f"🏁 [交单] 完成任务: {item_name}")
    
    except Exception as e_main:
        logger.error(f"❌ 致命错误: {e_main}")
    
    return brand_id

def run_infinite_loop():
    # 2. 启动浏览器矩阵 (保持原有的 DrissionPage 逻辑)
    pool.start_all()
    prepare_login_environment()

    logger.info("🤖 0404 分布式爬虫节点已上线，正在静默等待云端派单...")

    while True:
        try:
            # 3. 🔥 [核心改动] 阻塞式抢单 (BRPOP)
            # 它会静默等待，不消耗 CPU，直到云端 Redis 出现任务
            task_data = r_client.brpop("crawler_task_queue", timeout=0)
            
            if task_data:
                # task_data 格式为 ('crawler_task_queue', '{"brand_id": 123, ...}')
                _, task_json = task_data
                assigned_task = json.loads(task_json)
                
                brand_id = assigned_task.get('brand_id')
                item_name = assigned_task.get('item_name', '未知商品')
                server_ip = assigned_task.get('server_ip', 'unknown') # 👈 提取发起请求的服务器身份
                
                logger.info(f"🔗 [调度] 抢单成功: {item_name} (ID: {brand_id}, 发起方: {server_ip})")
                
                # ==========================================================
                # 🔥 [新增] 1. 全局缓存检查：别人找过了，我就直接“白嫖”
                # ==========================================================
                cached_result = check_global_cache(brand_id)
                if cached_result:
                    logger.info(f"✨ [秒回传] 命中全局缓存！无需弹窗抓取，直接为服务器 {server_ip} 复制结果")
                    
                    # 把缓存里的供应商数据合并进当前任务包
                    assigned_task.update(cached_result)
                    
                    # 假装是自己刚抓完的，直接写回数据库，状态标为成功
                    save_task_result(assigned_task, status='completed', custom_reason="系统自动复用全局同步缓存")
                    
                    # 发送完工信号给 05_AI 节点
                    clear_retry_placeholder(brand_id, server_ip)
                    
                    logger.info(f"💤 缓存同步完毕，继续监听下一单...")
                    continue # 👈 极其重要：直接跳回 while 循环开头，不执行下面的 process_whole_task！

                # ==========================================================
                # 2. 如果没缓存，才调用原有的浏览器矩阵去网页上硬抓
                # ==========================================================
                logger.info(f"🔎 未命中缓存，即将唤醒浏览器执行全网寻源...")
                process_whole_task(assigned_task)
                
                logger.info(f"💤 任务处理完毕，继续监听队列...")

        except Exception as e:
            logger.error(f"💥 分布式主循环出错: {e}")
            time.sleep(5)

if __name__ == "__main__":
    run_infinite_loop()