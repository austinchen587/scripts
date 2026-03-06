import select, psycopg2, threading, time
from config import DB_CONFIG as LOCAL_DB_CONFIG

local_event = threading.Event()

def _worker():
    while True:
        conn = None
        try:
            conn = psycopg2.connect(**LOCAL_DB_CONFIG)
            conn.set_isolation_level(psycopg2.extensions.ISOLATION_LEVEL_AUTOCOMMIT)
            cur = conn.cursor()
            cur.execute("LISTEN local_sku_channel;")
            print("👂 [LocalListener] 已连上本地库，静默等待爬虫回传价格...")
            while True:
                if select.select([conn], [], [], 60) == ([], [], []): continue
                conn.poll()
                while conn.notifies:
                    notify = conn.notifies.pop(0)
                    print(f"\n⚡ [LocalListener] 爬虫已写入新价格，瞬间唤醒 AI 选品！")
                    local_event.set()
        except Exception: time.sleep(5)
        finally:
            if conn:
                try: conn.close()
                except: pass

def start_listener():
    threading.Thread(target=_worker, daemon=True).start()
    return local_event