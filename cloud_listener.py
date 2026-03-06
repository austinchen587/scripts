# cloud_listener.py
import select
import psycopg2
import threading
import time

CLOUD_DB_CONFIG = {
    'host': '121.41.76.252',
    'port': '5432',
    'dbname': 'austinchen587_db',
    'user': 'austinchen587',
    'password': 'austinchen587',
    'connect_timeout': 10,
    # 【新增底层防断网配置】开启 TCP Keepalive 操作系统级保活
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
            
            cur.execute("LISTEN master_pipeline_channel;")
            print(f"👂 [CloudListener] 已连接云端，静默等待指令 (已开启防断网心跳)...")

            while True:
                # 每 60 秒苏醒一次，检查有没有信号
                if select.select([conn], [], [], 60) == ([], [], []):
                    # 【核心修复：应用层心跳】每60秒发一个极轻量的查询，保持TCP通道绝对活跃！
                    # 如果网络真的断了，这句代码会报错，从而触发下面的 except 自动重连
                    cur.execute("SELECT 1;") 
                    continue
                
                conn.poll()
                while conn.notifies:
                    notify = conn.notifies.pop(0)
                    print(f"\n⚡ [CloudListener] 收到云端信号: {notify.payload}，唤醒流水线！")
                    cloud_event.set()
                    
        except Exception as e:
            print(f"❌ [CloudListener] 连接异常断开: {e}，5秒后自动重连...")
            time.sleep(5)
        finally:
            if conn: 
                try: conn.close() 
                except: pass

def start_listener():
    t = threading.Thread(target=_worker, daemon=True)
    t.start()
    return cloud_event