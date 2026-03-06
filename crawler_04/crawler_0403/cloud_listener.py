import select, psycopg2, threading, time

CLOUD_DB_CONFIG = {
    'host': '121.41.128.53', 'port': '5432',
    'dbname': 'austinchen587_db', 'user': 'austinchen587', 'password': 'austinchen587', 'connect_timeout': 10
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
            print("👂 [CloudListener] 已连上云端 (128.53)，静默等待新任务...")
            while True:
                if select.select([conn], [], [], 60) == ([], [], []): continue
                conn.poll()
                while conn.notifies:
                    notify = conn.notifies.pop(0)
                    print(f"\n⚡ [CloudListener] 收到云端信号: {notify.payload}，唤醒爬虫！")
                    cloud_event.set()
        except Exception: time.sleep(5)
        finally:
            if conn:
                try: conn.close()
                except: pass

def start_listener():
    threading.Thread(target=_worker, daemon=True).start()
    return cloud_event