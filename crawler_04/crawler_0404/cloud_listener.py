# cloud_listener.py
import select, psycopg2, threading, time

# 配置统一使用本地 127.0.0.1
CLOUD_DB_CONFIG = {
    'host': '127.0.0.1', 
    'port': '5432',
    'dbname': 'austinchen587_db', 
    'user': 'austinchen587', 
    'password': 'austinchen587', 
    'connect_timeout': 10,
    # 开启 TCP 保活，防止长连接被系统回收
    'keepalives': 1,
    'keepalives_idle': 30,
    'keepalives_interval': 10,
    'keepalives_count': 5
}

# 【修复 1】变量名改为 cloud_event，与 main.py 保持一致
cloud_event = threading.Event()

def _worker():
    while True:
        conn = None
        try:
            # 【修复 2】这里必须引用上面定义的 CLOUD_DB_CONFIG
            conn = psycopg2.connect(**CLOUD_DB_CONFIG)
            
            # 必须设置为 AUTOCOMMIT 才能接收 LISTEN 异步通知
            conn.set_isolation_level(psycopg2.extensions.ISOLATION_LEVEL_AUTOCOMMIT)
            
            cur = conn.cursor()
            # 监听频道名（对应 main.py 中的信号名）
            cur.execute("LISTEN crawler_channel;")
            print(f"👂 [CloudListener] 已连上本地库，正在监听云端指令 [crawler_channel]...")
            
            while True:
                # 60秒心跳检查
                if select.select([conn], [], [], 60) == ([], [], []):
                    cur.execute("SELECT 1;")
                    continue
                
                conn.poll()
                while conn.notifies:
                    notify = conn.notifies.pop(0)
                    print(f"⚡ [CloudListener] 收到信号: {notify.payload}")
                    # 【修复 3】对应上面的变量名
                    cloud_event.set()
                    
        except Exception as e:
            print(f"❌ [CloudListener] 发生错误: {e}，5秒后重连...")
            time.sleep(5)
        finally:
            if conn:
                try: conn.close()
                except: pass

def start_listener():
    t = threading.Thread(target=_worker, daemon=True)
    t.start()
    # 【修复 4】返回正确的 event 对象
    return cloud_event