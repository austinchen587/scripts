# D:\code\project\scripts\master_daemon.py
import subprocess
import time
import sys
import os
import datetime
import logging
import threading
import queue
from cloud_listener import start_listener, cloud_event
import psycopg2

# === 基础配置 ===
BASE_DIR = r"D:\code\project\scripts"

# 定义任务流程 (超时限制:1分钟)
TASKS = [
    {
        "name": "Step 0: 数据同步 (Cloud->Local)",
        "cwd": os.path.join(BASE_DIR, "sync_procurement"),
        "script": "sync_procurement.py",
        "args": ["--once"],
        "timeout": 1800
    },
    {
        "name": "Step 1: 业务分类",
        "cwd": os.path.join(BASE_DIR, "20251227", "20260109_step_1"),
        "script": "auto_launcher.py",
        "args": [],
        "timeout": 1800
    },
    {
        "name": "Step 2: 深度解析 (LLM)",
        "cwd": os.path.join(BASE_DIR, "20260111_step_2"),
        "script": "auto_launcher.py",
        "args": [],
        "timeout": 3600
    },
    {
        "name": "Step 3: 平台决策与搜索词",
        "cwd": os.path.join(BASE_DIR, "procurement_ai_processor"),
        "script": "auto_launcher.py",
        "args": [],
        "timeout": 1800
    },
    {
        "name": "Step 4: 数据回传 (Local->Cloud)",
        "cwd": os.path.join(BASE_DIR, "sync_procurement"),
        "script": "upload_results.py",
        "args": [],
        "timeout": 1800
    }
]

# === 日志配置 ===
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - [MASTER] - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(os.path.join(BASE_DIR, 'master_daemon.log'), encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger("Master")

def enqueue_output(out, q):
    """辅助线程：非阻塞读取子进程输出"""
    for line in iter(out.readline, ''):
        q.put(line)
    out.close()

def run_task(task_config):
    """运行单个任务子进程（非阻塞读取日志 + 超时熔断）"""
    name = task_config["name"]
    script_path = os.path.join(task_config["cwd"], task_config["script"])
    timeout_sec = task_config.get("timeout", 1800) # 默认30分钟
    
    if not os.path.exists(script_path):
        logger.error(f"❌ 找不到脚本: {script_path}")
        return False

    logger.info(f"▶️  正在启动: {name} (超时限制: {timeout_sec/60:.0f}分钟)")
    print("-" * 40)
    
    start_time = time.time()
    
    try:
        cmd = [sys.executable, task_config["script"]] + task_config["args"]
        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"

        process = subprocess.Popen(
            cmd,
            cwd=task_config["cwd"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding='utf-8',
            errors='replace',
            env=env,
            bufsize=1
        )
        
        # 使用队列实现非阻塞读取
        q = queue.Queue()
        t = threading.Thread(target=enqueue_output, args=(process.stdout, q))
        t.daemon = True
        t.start()
        
        last_lines = []
        is_timeout = False

        # === 实时监控循环 ===
        while True:
            # 1. 检查超时
            current_duration = time.time() - start_time
            if current_duration > timeout_sec:
                logger.error(f"\n[TIMEOUT] ⏳ {name} 运行时间超过 {timeout_sec/60:.0f} 分钟，强制终止！")
                process.kill()
                is_timeout = True
                break

            # 2. 读取日志 (非阻塞)
            try:
                line = q.get_nowait()
                print(f"    | {line.rstrip()}")
                if len(line.strip()) > 0:
                    last_lines.append(line.rstrip())
                    if len(last_lines) > 20:
                        last_lines.pop(0)
            except queue.Empty:
                # 检查进程是否结束
                if process.poll() is not None:
                    break
                # 短暂休眠避免CPU空转
                time.sleep(0.1)

        # === 结束处理 ===
        duration = time.time() - start_time
        print("-" * 40)

        if is_timeout:
            logger.warning(f"⚠️ {name} 因超时被熔断 (耗时 {duration:.1f}s)")
            return False

        return_code = process.poll()
        if return_code == 0:
            logger.info(f"✅ {name} 完成 (耗时 {duration:.1f}s)")
            return True
        else:
            logger.error(f"❌ {name} 失败 (代码 {return_code})")
            logger.error("    最后日志片段:")
            for l in last_lines:
                logger.error(f"    | {l}")
            return False

    except Exception as e:
        logger.error(f"❌ {name} 执行异常: {e}")
        return False

LOCAL_DB_CONFIG = {       # 👈 确保这里名字是 LOCAL_DB_CONFIG
    'host': 'localhost',  
    'port': '5432',
    'dbname': 'austinchen587_db',
    'user': 'austinchen587',
    'password': 'austinchen587',
    'connect_timeout': 5
}

def has_pending_tasks():
    """睡觉前的最后检查：本地碗里还有饭吗？"""
    query = """
    SELECT COUNT(*)
    FROM procurement_emall_category pec
    JOIN procurement_emall pe ON pec.record_id = pe.id
    WHERE pec.category = 'goods'
    AND pe.id NOT IN (SELECT procurement_id FROM procurement_commodity_category)
    """
    try:
        with psycopg2.connect(**LOCAL_DB_CONFIG) as conn:
            with conn.cursor() as cur:
                cur.execute(query)
                count = cur.fetchone()[0]
                if count > 0:
                    logger.info(f"📊 本地数据库还有 {count} 条未处理数据...")
                return count > 0
    except Exception as e:
        logger.error(f"❌ 检查剩余任务失败: {e}")
        return False

def main_loop():
    print("=" * 60)
    print("🤖 采购业务全自动集成系统 (事件驱动 + 排空机制版)")
    print("流程: 下拉 -> 分类 -> 解析 -> 推荐 -> 上传 -> 排空/休眠")
    print("=" * 60)

    # 1. 启动后台监听线程
    start_listener()

    # 【核心修复 1】使用 skip_sleep 作为状态开关
    skip_sleep = True

    while True:
        # ==========================================
        # 挂起逻辑：只有当 skip_sleep 为 False 时才休眠
        # ==========================================
        if not skip_sleep:
            safe_fallback_minutes = 360 # 6小时
            logger.info(f"💤 任务已清空，流水线进入休眠等待... (兜底巡检: {safe_fallback_minutes}分钟)")
            
            try:
                # 阻塞等待云端信号
                is_woken = cloud_event.wait(timeout=safe_fallback_minutes * 60)
                
                if is_woken:
                    logger.info("🎯 [极速响应] 收到云端指令，立即启动！")
                    cloud_event.clear() # 重置信号灯
                else:
                    logger.info("⏳ [安全巡检] 达到兜底时间，执行例行检查...")
            
            except KeyboardInterrupt:
                logger.info("🛑 用户终止程序")
                break
                
        # 【核心修复 2】无论如何，默认下一轮要休眠（除非排空机制说不）
        skip_sleep = False

        # ==========================================
        # 核心业务流水线：开始干活
        # ==========================================
        cycle_start = datetime.datetime.now()
        logger.info(f"\n🕒 === 开始新一轮循环: {cycle_start.strftime('%Y-%m-%d %H:%M:%S')} ===")
        
        for task in TASKS:
            success = run_task(task)
            if not success:
                logger.warning(f"⚠️ {task['name']} 未能正常完成，尝试继续执行后续步骤...")
            time.sleep(2) 

        logger.info(f"✅ 本轮循环结束")

        # ==========================================
        # 【排空机制】干完活后，检查数据库
        # ==========================================
        if has_pending_tasks():
            logger.info("📦 检测到云端数据库中还有剩余任务！跳过休眠，直接连轴转处理下一批...")
            # 【核心修复 3】发现还有任务，把开关设为 True，下一轮就不会进休眠区块了！
            skip_sleep = True
            continue

if __name__ == "__main__":
    main_loop()