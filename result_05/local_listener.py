# local_listener.py
import select, psycopg2, threading, time
from config import DB_CONFIG as LOCAL_DB_CONFIG

local_event = threading.Event()

def _worker():
    while True:
        conn = None
        try:
            # 建立本地连接
            conn = psycopg2.connect(**LOCAL_DB_CONFIG)
            # 必须设置为自动提交才能监听信号
            conn.set_isolation_level(psycopg2.extensions.ISOLATION_LEVEL_AUTOCOMMIT)
            cur = conn.cursor()
            
            # 监听本地频道
            cur.execute("LISTEN local_sku_channel;")
            print("👂 [LocalListener] 已连上本地库，静默等待爬虫回传价格 (心跳已开启)...")
            
            while True:
                # 每 60 秒苏醒一次
                if select.select([conn], [], [], 60) == ([], [], []):
                    # 【核心保活】发送一个微型查询，确保本地连接没死
                    cur.execute("SELECT 1;")
                    continue
                
                conn.poll()
                while conn.notifies:
                    notify = conn.notifies.pop(0)
                    print(f"\n⚡ [LocalListener] 爬虫已写入新价格，唤醒 AI 选品！")
                    local_event.set() # 摇铃，唤醒主循环
                    
        except Exception as e:
            print(f"❌ [LocalListener] 本地监听异常: {e}，5秒后自动重连...")
            time.sleep(5)
        finally:
            if conn:
                try: conn.close()
                except: pass

def start_listener():
    t = threading.Thread(target=_worker, daemon=True)
    t.start()
    return local_event