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

# ================= 配置区域 =================
WORK_DURATION = 4 * 60 * 60 
REST_DURATION = 30 * 60
# 必须与 browser_manager 中的浏览器数量保持一致
MAX_WORKERS = 1

# [新增配置] 无数据时，重新同步云端数据库的间隔时间 (秒)
NO_DATA_SYNC_INTERVAL = 2 * 60 
# ===========================================

# 内存锁：记录正在处理中的 Brand_ID，防止重复领取
PROCESSING_BRAND_IDS = set()
# [新增] 内存锁：记录 浏览器名称 与 采购项目ID 的绑定关系 (1个浏览器=1个项目)
BROWSER_PROJECT_MAP = {}

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
    logger.info("🔓 [系统启动] 正在唤醒所有浏览器...")
    for browser in pool.browsers:
        try:
            get_or_create_tab(browser, 'jd.com', 'https://www.jd.com/')
            get_or_create_tab(browser, 'taobao.com', 'https://www.taobao.com/')
            get_or_create_tab(browser, '1688.com', 'https://www.1688.com/')
        except Exception: pass

    logger.info("🛑 [静默等待模式] 请登录并搜索任意词 (如 '1')...")
    while True:
        all_ready, not_ready_names = pool.check_all_browsers_ready()
        if all_ready:
            logger.info("✅ 所有浏览器就绪！")
            break
        time.sleep(2)
    logger.info("⏳ 倒计时 10秒 开跑...")
    time.sleep(10)

def process_whole_task(browser, task):
    """
    [核心工人类] 
    返回: browser 对象和 brand_id (以便主线程精准释放内存锁)
    """
    b_name = getattr(browser, '_custom_name', 'Unknown')
    kw = task['key_word']
    pid = task['procurement_id']
    item_name = task['item_name']
    brand_id = task.get('brand_id')
    
    # 获取目标平台，去除两端空白
    target_str = task.get('search_platform', '') or ''
    target_str = target_str.strip()

    logger.info(f"🔥 [领单] {b_name} 开始处理: {item_name} (ID: {brand_id})")

    all_platforms = [
        ('京东', JDEngine),
        ('1688', S1688Engine),
        ('淘宝', TaobaoEngine)
    ]
    
    # 决定要搜索的平台列表
    platforms_to_search = []
    if target_str:
        # 优先按照推荐平台搜索
        for p_name, p_class in all_platforms:
            if p_name in target_str:
                platforms_to_search.append((p_name, p_class))
        
        # 兜底检测：如果数据库传来的名字写错了(比如传了'拼多多')，随机选一个
        if platforms_to_search:
            logger.info(f"🎯 [目标平台] 系统指定: {[p[0] for p in platforms_to_search]}")
        else:
            chosen_platform = random.choice(all_platforms)
            platforms_to_search.append(chosen_platform)
            logger.info(f"🎯 [目标平台] 指定平台无效，随机单选兜底: {chosen_platform[0]}")
    else:
        # 如果没有推荐平台，随机挑选1个平台
        chosen_platform = random.choice(all_platforms)
        platforms_to_search.append(chosen_platform)
        logger.info(f"🎯 [目标平台] 无推荐，随机单选: {chosen_platform[0]}")

    has_any_result = False

    try:
        # 遍历确定的平台列表执行抓取
        for platform_name, EngineClass in platforms_to_search:
            
            time.sleep(random.uniform(1.5, 3))
            logger.info(f"   👉 {b_name} -> [{platform_name}]")
            
            # ==========================================
            # 👉 [新增快照] 抓取前，记录当前有哪些标签页
            # ==========================================
            try:
                initial_tab_ids = browser.tab_ids
            except:
                initial_tab_ids = getattr(browser, '_tab_ids', [])
            
            try:
                engine = EngineClass(browser)
                raw_data = engine.search(kw)
                
                if raw_data:
                    logger.info(f"      ✅ {b_name} [{platform_name}] 抓取 {len(raw_data)} 条")
                    clean_records = process_and_map(raw_data, pid, item_name)
                    for r in clean_records:
                        r['brand_id'] = brand_id
                    save_skus_to_db(clean_records)
                    has_any_result = True
                else:
                    logger.info(f"      ⭕ {b_name} [{platform_name}] 未抓取到数据")
                    
            except Exception as e:
                logger.error(f"      💥 {b_name} [{platform_name}] 抓取过程出错: {e}")
                
            # ==========================================
            # 👉 [新增清理] 抓取后(无论成功失败)，关掉新冒出来的标签页
            # 使用 finally 确保哪怕上面报错了，这里也一定会执行
            # ==========================================
            finally:
                try:
                    try:
                        current_tab_ids = browser.tab_ids
                    except:
                        current_tab_ids = getattr(browser, '_tab_ids', [])

                    # 找出多出来的标签页并强制关闭
                    for t_id in current_tab_ids:
                        if t_id not in initial_tab_ids:
                            try:
                                logger.info(f"   🧹 {b_name} 清理残留的详情页/新窗口...")
                                tab_to_close = browser.get_tab(t_id)
                                if tab_to_close:
                                    tab_to_close.close()
                            except:
                                pass
                    
                    # 确保切回最初的那个工作标签页，防止浏览器失去焦点卡死
                    if initial_tab_ids:
                        try:
                            target_tab = browser.get_tab(initial_tab_ids[-1])
                            if target_tab:
                                if hasattr(browser.set, 'tab'):
                                    browser.set.tab(target_tab)
                                else:
                                    target_tab.activate()
                        except:
                            pass
                except Exception as cleanup_err:
                    logger.error(f"      💥 {b_name} 清理标签页时出错: {cleanup_err}")

        # 结算逻辑
        if has_any_result:
            clear_retry_placeholder(brand_id)
        else:
            logger.warning(f"🚫 {b_name} 任务 [{item_name}] 无结果，标记人工审核。")
            save_failed_task(task)
        
        logger.info(f"🏁 [交单] {b_name} 完成任务: {item_name}")
    
    except Exception as e_main:
        logger.error(f"❌ {b_name} 致命错误: {e_main}")
    
    return browser, brand_id

def run_infinite_loop():
    last_sync_time = time.time()
    
    # --- [阶段 1] 启动前初始同步与清理 ---
    try:
        if hasattr(db_sync, 'run_sync_download'): 
            db_sync.run_sync_download()
            # === 核心修复：启动同步后立即执行本地重试任务清理 ===
            if hasattr(db_sync, 'cleanup_local_retry_cache'):
                db_sync.cleanup_local_retry_cache()
            # ===============================================
            last_sync_time = time.time()
    except Exception as e:
        logger.error(f"❌ 初始同步/清理失败: {e}")

    pool.start_all()
    prepare_login_environment()

    logger.info(f"🚀 开启 {MAX_WORKERS} 线程并发 (项目隔离流水线模式)...")
    current_cycle_start_time = time.time()

    executor = ThreadPoolExecutor(max_workers=MAX_WORKERS)
    
    idle_browsers = list(pool.browsers)
    running_futures = set()

    while True:
        try:
            # --- A. 强制休息逻辑 ---
            if time.time() - current_cycle_start_time > WORK_DURATION:
                logger.info("⏰ 达到工作时限，等待当前任务全部结束后休息...")
                wait(running_futures) 
                running_futures.clear()
                idle_browsers = list(pool.browsers) 
                PROCESSING_BRAND_IDS.clear() 
                BROWSER_PROJECT_MAP.clear() 
                
                logger.info(f"⏰ 开始休息 {REST_DURATION/60} 分钟...")
                time.sleep(REST_DURATION)
                current_cycle_start_time = time.time()
                
                # 休息结束后的例行同步与清理
                try: 
                    if hasattr(db_sync, 'run_sync_download'):
                        db_sync.run_sync_download()
                        if hasattr(db_sync, 'cleanup_local_retry_cache'):
                            db_sync.cleanup_local_retry_cache()
                        last_sync_time = time.time()
                except: pass

            # --- B. 补货逻辑：项目隔离抢单 ---
            if idle_browsers:
                # get_pending_tasks 会因为上一步的清理逻辑重新识别出 retry 的任务
                pending_candidates = get_pending_tasks() 
                
                valid_tasks = []
                for t in pending_candidates:
                    bid = t.get('brand_id')
                    if bid not in PROCESSING_BRAND_IDS:
                        valid_tasks.append(t)
                
                for browser in list(idle_browsers):
                    b_name = getattr(browser, '_custom_name', 'Unknown')
                    assigned_task = None
                    active_pid = BROWSER_PROJECT_MAP.get(b_name)
                    
                    if active_pid:
                        for t in valid_tasks:
                            if t['procurement_id'] == active_pid:
                                assigned_task = t
                                break
                        if not assigned_task:
                            del BROWSER_PROJECT_MAP[b_name]
                            active_pid = None 
                    
                    if not active_pid:
                        active_pids_of_others = set(BROWSER_PROJECT_MAP.values())
                        for t in valid_tasks:
                            if t['procurement_id'] not in active_pids_of_others:
                                assigned_task = t
                                BROWSER_PROJECT_MAP[b_name] = t['procurement_id'] 
                                break
                    
                    if assigned_task:
                        brand_id = assigned_task.get('brand_id')
                        PROCESSING_BRAND_IDS.add(brand_id)
                        idle_browsers.remove(browser)
                        valid_tasks.remove(assigned_task)
                        
                        logger.info(f"🔗 [调度] {b_name} 绑定项目 {assigned_task['procurement_id']} -> 领单: {assigned_task['item_name']}")
                        f = executor.submit(process_whole_task, browser, assigned_task)
                        running_futures.add(f)

            # --- C. 等待逻辑与周期性同步机制 ---
            if not running_futures:
                time_since_last_sync = time.time() - last_sync_time
                if time_since_last_sync >= NO_DATA_SYNC_INTERVAL:
                    logger.info(f"📡 本地无任务已达 {NO_DATA_SYNC_INTERVAL/60:.0f} 分钟，触发云端同步拉取新任务...")
                    try:
                        if hasattr(db_sync, 'run_sync_download'):
                            db_sync.run_sync_download()
                            # === 核心修复：周期同步后也立即执行清理 ===
                            if hasattr(db_sync, 'cleanup_local_retry_cache'):
                                db_sync.cleanup_local_retry_cache()
                            # =======================================
                    except Exception as e:
                        logger.error(f"❌ 自动同步失败: {e}")
                    last_sync_time = time.time() 
                else:
                    logger.info("💤 全员空闲且无新任务，休息 10 秒...")
                    time.sleep(10)
                continue
            
            # --- D. 结算回收逻辑 ---
            done, not_done = wait(running_futures, return_when=FIRST_COMPLETED)
            
            for future in done:
                running_futures.remove(future) 
                try:
                    free_browser, completed_brand_id = future.result()
                    idle_browsers.append(free_browser)
                    
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