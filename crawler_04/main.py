# main.py
import time
import random
import db_sync 
from db_helper import get_pending_tasks, save_skus_to_db
from engines.jd_engine import JDEngine
from engines.s1688_engine import S1688Engine
from engines.taobao_engine import TaobaoEngine
from processor import process_and_map
from logger_helper import logger

def create_placeholder_record(pid, platform, kw, item_name):
    """
    创建一个'未找到商品'的占位记录
    """
    return {
        'procurement_id': pid,
        'sku': 'NO_RESULT',          
        'platform': platform,
        'title': f'【无搜索结果】{kw}', 
        'price': 0,
        'shop_name': 'System_Auto_Mark',
        'sales': '0',
        'detail_url': 'N/A',
        'hot_info': '系统自动标记：未搜索到有效商品',
        'item_name': item_name       
    }

def safe_upload():
    """安全回传封装，将数据推送到配置的内网服务器"""
    try:
        if hasattr(db_sync, 'run_sync_upload'):
            logger.info("📤 [即时同步] 正在将最新结果回传至内网服务器...")
            db_sync.run_sync_upload()
        else:
            logger.warning("⚠️ db_sync.py 中未找到 run_sync_upload 方法，跳过回传。")
    except Exception as e:
        logger.error(f"❌ 即时回传失败: {e} (不影响爬虫继续运行)")

def run_infinite_loop():
    # --- [阶段 1] 启动前同步云端数据库 (Cloud -> Local) ---
    try:
        logger.info("🔄 正在初始化：执行基础数据下载同步...")
        if hasattr(db_sync, 'run_sync_download'):
            db_sync.run_sync_download()
        else:
            db_sync.run_sync()
        logger.info("✅ 数据库同步完成，准备启动爬虫。")
    except Exception as e:
        logger.error(f"❌ 数据库同步发生错误，但不影响爬虫主进程继续运行: {e}")

    logger.info("🚀 Automation Crawler Started (Infinite Loop Mode)")
    
    # --- [阶段 2] 进入无限循环任务 ---
    while True:
        try:
            logger.info("🔍 Checking for pending tasks...")
            tasks = get_pending_tasks() 
            
            # --- 场景 1: 数据库没任务 (待机模式) ---
            if not tasks:
                logger.info("💤 No pending tasks found. Sleeping for 60 seconds...")
                time.sleep(60)
                continue 

            # --- 场景 2: 有任务，开始干活 ---
            logger.info(f"📋 锁定前3个项目，本轮共计 {len(tasks)} 个商品任务")
            
            engines = {
                '京东': JDEngine(), 
                '1688': S1688Engine(),
                '淘宝': TaobaoEngine()
            }

            for idx, task in enumerate(tasks, 1):
                kw, platform, pid, item_name = task['key_word'], task['search_platform'], task['procurement_id'], task['item_name']
                
                # === 拼多多流量分发 ===
                if platform == '拼多多':
                    new_target = random.choice(['1688', '淘宝'])
                    logger.info(f"🔀 [Redirect] 检测到 '拼多多' 任务，随机分配给 -> {new_target}")
                    platform = new_target

                # 检查引擎支持情况
                if not kw or platform not in engines or not engines[platform]:
                    logger.warning(f"[{idx}/{len(tasks)}] ⏭ Skip: '{kw}' (Platform {platform} not supported)")
                    continue

                logger.info(f"[{idx}/{len(tasks)}] ⏳ Processing: {platform} -> {kw} (ID: {pid}, Item: {item_name})")
                
                task_start_time = time.time()
                
                try:
                    # 1. 执行搜索
                    raw_data = engines[platform].search(kw)
                    
                    # 2. 数据清洗
                    clean_records = []
                    if raw_data:
                        clean_records = process_and_map(raw_data, pid, item_name)
                    
                    # 3. 入库逻辑分流
                    if clean_records:
                        # A. 正常情况
                        save_skus_to_db(clean_records)
                        duration = time.time() - task_start_time
                        logger.info(f"✅ Success! Captured {len(clean_records)} items | Time: {duration:.2f}s")
                        
                        # [即时回传] 成功入库后，推送到内网服务器
                        safe_upload()
                        
                    else:
                        # B. 异常情况
                        logger.warning(f"⚠️ [No Result] 未找到有效商品 '{kw}'，写入占位数据以防死循环。")
                        
                        placeholder = create_placeholder_record(pid, platform, kw, item_name)
                        save_skus_to_db([placeholder])
                        logger.info(f"💾 已保存占位记录，该任务将被标记为完成。")
                        
                        # [即时回传] 占位数据也需要回传
                        safe_upload()

                except Exception as e:
                    logger.error(f"💥 Exception during task processing: {e}", exc_info=True)

                # --- 任务间的小休息 (防风控) ---
                if idx < len(tasks):
                    wait_time = random.uniform(60, 120)
                    logger.info(f"💤 任务完成，随机静默 {wait_time:.1f} 秒...")
                    time.sleep(wait_time)

            # --- 场景 3: 本轮任务结束 ---
            logger.info("🎉 本轮所有任务已完成。")
            
            # 每一轮大循环结束后，休息较长时间
            round_wait = random.uniform(120, 150)
            logger.info(f"🍵 大循环结束，休息 {round_wait:.1f} 秒 (约2分钟) 后开始下一轮检测...")
            time.sleep(round_wait)

        except KeyboardInterrupt:
            logger.warning("🛑 程序被手动停止 (User Stopped)")
            # [退出回传]
            logger.info("🚑 [紧急] 正在尝试退出前的数据回传...")
            safe_upload()
            break
            
        except Exception as e:
            logger.error(f"💥 Critical Main Loop Error: {e}", exc_info=True)
            logger.info("⚠️ 发生严重错误，休眠 60 秒后尝试重启...")
            time.sleep(60)

if __name__ == "__main__":
    run_infinite_loop()