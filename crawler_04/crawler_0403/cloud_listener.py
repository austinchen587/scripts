# cloud_listener.py
import select, psycopg2, threading, time

CLOUD_DB_CONFIG = {
    'host': '121.41.128.53', 
    'port': '5432',
    'dbname': 'austinchen587_db', 
    'user': 'austinchen587', 
    'password': 'austinchen587', 
    'connect_timeout': 10,
    # 【核心修复 1】开启操作系统级 TCP 保活
    'keepalives': 1,
    'keepalives_idle': 30,
    'keepalives_interval': 10,
    'keepalives_count': 5
}
cloud_event = threading.Event()

def _worker():
    while True:
        conn = None
        try:
            conn = psycopg2.connect(**CLOUD_DB_CONFIG)
            conn.set_isolation_level(psycopg2.extensions.ISOLATION_LEVEL_AUTOCOMMIT)
            cur = conn.cursor()
            cur.execute("LISTEN crawler_channel;")
            print("👂 [CloudListener] 已连上云端 (128.53)，静默等待新任务 (防断网心跳已开启)...")
            
            while True:
                # 每 60 秒检查一次连接
                if select.select([conn], [], [], 60) == ([], [], []):
                    # 【核心修复 2】应用层心跳：每分钟发一次极简查询，强行保持链路活跃
                    cur.execute("SELECT 1;")
                    continue
                
                conn.poll()
                while conn.notifies:
                    notify = conn.notifies.pop(0)
                    print(f"\n⚡ [CloudListener] 收到云端信号: {notify.payload}，唤醒爬虫！")
                    cloud_event.set()
                    
        except Exception as e:
            print(f"❌ [CloudListener] 连接断开: {e}，5秒后重连...")
            time.sleep(5)
        finally:
            if conn:
                try: conn.close()
                except: pass

def start_listener():
    t = threading.Thread(target=_worker, daemon=True)
    t.start()
    return cloud_event