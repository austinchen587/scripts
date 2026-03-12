# main.py
import time
import random
from concurrent.futures import ThreadPoolExecutor, wait, FIRST_COMPLETED
from browser_manager import pool 
import db_sync 
from engines.jd_engine import JDEngine
from engines.s1688_engine import S1688Engine
from engines.taobao_engine import TaobaoEngine
from processor import process_and_map
from logger_helper import logger
from db_helper import get_pending_tasks, save_skus_to_db, save_failed_task, clear_retry_placeholder
from engines.base_engine import AntiSpiderException
from cloud_listener import start_listener, cloud_event

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
    
    # 删除了那个容易卡死的 while True 自动检测，改为人工确认
    input("👉 浏览器操作完成后，请在此黑窗口【按下 Enter 回车键】放行...")
    
    logger.info("✅ 所有浏览器就绪！")
    logger.info("⏳ 倒计时 3秒 开跑...")
    time.sleep(3) # 既然人工确认了，倒计时可以缩短点

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

            except AntiSpiderException as anti_spider_err:
                logger.warning(f"⚠️ [{b_name}] 被拦截: {anti_spider_err}")
                PLATFORM_COOLDOWN[platform_name] = time.time() + COOLDOWN_TIME
                logger.error(f"🛑 [专属通道熔断] {platform_name} 在接下来的 {COOLDOWN_TIME/60:.0f} 分钟内将被隔离！")
                
                logger.info(f"🧹 [{b_name}] 正在自愈清洗专属缓存 (保留登录状态)...")
                try:
                    browser.clear_cache(cookies=False, history=False)
                    browser.get("https://www.baidu.com")
                    time.sleep(random.uniform(2, 4))
                except Exception as clear_err:
                    logger.error(f"      💥 [{b_name}] 清理缓存出错: {clear_err}")
                
                task['status'] = 'retry'
                save_failed_task(task)
                break 

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

        if has_any_result:
            clear_retry_placeholder(brand_id)
        elif task.get('status') == 'retry':
            pass 
        elif skipped_due_to_cooldown:
            logger.info(f"🔄 任务 [{item_name}] 因目标平台全在冷却中，主动挂起重试。")
            task['status'] = 'retry'
            save_failed_task(task)
        else:
            logger.warning(f"🚫 任务 [{item_name}] 无结果，标记人工审核。")
            save_failed_task(task)
        
        logger.info(f"🏁 [交单] 完成任务: {item_name}")
    
    except Exception as e_main:
        logger.error(f"❌ 致命错误: {e_main}")
    
    return brand_id

def run_infinite_loop():
    last_sync_time = time.time()
    
    try:
        if hasattr(db_sync, 'run_sync_download'): 
            db_sync.run_sync_download()
            if hasattr(db_sync, 'cleanup_local_retry_cache'):
                db_sync.cleanup_local_retry_cache()
            last_sync_time = time.time()
    except Exception as e:
        logger.error(f"❌ 初始同步/清理失败: {e}")

    pool.start_all()
    prepare_login_environment()

    logger.info(f"🚀 开启 1 线程调度 (底层3大浏览器隔离专线)...")
    current_cycle_start_time = time.time()

    # [新增] 启动云端发令枪监听
    start_listener()

    executor = ThreadPoolExecutor(max_workers=MAX_WORKERS)
    running_futures = set()

    while True:
        try:
            if time.time() - current_cycle_start_time > WORK_DURATION:
                logger.info("⏰ 达到工作时限，等待当前任务全部结束后休息...")
                wait(running_futures) 
                running_futures.clear()
                PROCESSING_BRAND_IDS.clear() 
                
                logger.info(f"⏰ 开始休息 {REST_DURATION/60} 分钟...")
                time.sleep(REST_DURATION)
                current_cycle_start_time = time.time()
                
                try: 
                    if hasattr(db_sync, 'run_sync_download'):
                        db_sync.run_sync_download()
                        if hasattr(db_sync, 'cleanup_local_retry_cache'):
                            db_sync.cleanup_local_retry_cache()
                        last_sync_time = time.time()
                except: pass

            if len(running_futures) < MAX_WORKERS:
                
                # ======================================================
                
                # 下面是你原本的代码，保持不变，作为优先级 2：
                pending_candidates = get_pending_tasks() 
                assigned_task = None
                
                for t in pending_candidates:
                    bid = t.get('brand_id')
                    if bid not in PROCESSING_BRAND_IDS:
                        assigned_task = t
                        break
                
                if assigned_task:
                    brand_id = assigned_task.get('brand_id')
                    PROCESSING_BRAND_IDS.add(brand_id)
                    logger.info(f"🔗 [调度] 领单: {assigned_task['item_name']}")
                    f = executor.submit(process_whole_task, assigned_task)
                    running_futures.add(f)

            if not running_futures:
                # 触发云端同步，把数据拉下来
                logger.info("📡 检查云端是否有新任务...")
                try:
                    if hasattr(db_sync, 'run_sync_download'):
                        db_sync.run_sync_download()
                        if hasattr(db_sync, 'cleanup_local_retry_cache'):
                            db_sync.cleanup_local_retry_cache()
                except Exception as e:
                    logger.error(f"❌ 自动同步失败: {e}")
                
                # 同步完再次检查本地有没有【真正可用】的任务
                pending_candidates = get_pending_tasks()
                has_new_task = False
                for t in pending_candidates:
                    if t.get('brand_id') not in PROCESSING_BRAND_IDS:
                        has_new_task = True
                        break
                        
                if not has_new_task:
                    logger.info("💤 本地和云端均无任务，爬虫挂起等待云端信号... (兜底巡检: 60分钟)")
                    # 彻底阻塞，0耗能等待
                    is_woken = cloud_event.wait(timeout=21600)
                    if is_woken:
                        logger.info("🎯 [极速响应] 收到云端发信，立刻唤醒爬虫！")
                        cloud_event.clear()
                continue
            
            done, not_done = wait(running_futures, return_when=FIRST_COMPLETED)
            
            for future in done:
                running_futures.remove(future) 
                try:
                    completed_brand_id = future.result()
                    if completed_brand_id in PROCESSING_BRAND_IDS:
                        PROCESSING_BRAND_IDS.remove(completed_brand_id)

                    if len(PROCESSING_BRAND_IDS) > 5000:
                        PROCESSING_BRAND_IDS.clear()

                except Exception as e:
                    logger.error(f"❌ 任务回收异常: {e}")

        except Exception as e:
            logger.error(f"💥 主循环错误: {e}")
            time.sleep(10)

if __name__ == "__main__":
    run_infinite_loop()