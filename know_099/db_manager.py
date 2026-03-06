# D:\code\project\scripts\know_099\db_manager.py
import psycopg2
from psycopg2.extras import DictCursor, execute_values
from config import DB_CONFIG, TABLE_NODES, TABLE_EDGES, TABLE_RESULT

class DBManager:
    def __init__(self):
        self.conn = psycopg2.connect(**DB_CONFIG)
        self.conn.autocommit = True

    def init_schema(self):
        """初始化架构"""
        with self.conn.cursor() as cur:
            cur.execute(f"""
                CREATE TABLE IF NOT EXISTS {TABLE_RESULT} (
                    id SERIAL PRIMARY KEY,
                    source_id INT UNIQUE NOT NULL,
                    status VARCHAR(20) DEFAULT 'success',
                    extracted_data JSONB,
                    processed_at TIMESTAMP DEFAULT NOW()
                );
                CREATE INDEX IF NOT EXISTS idx_res_source ON {TABLE_RESULT}(source_id);
            """)
            cur.execute(f"""
                CREATE TABLE IF NOT EXISTS {TABLE_NODES} (
                    id SERIAL PRIMARY KEY,
                    node_type VARCHAR(50), name VARCHAR(255),
                    properties JSONB, unique_key VARCHAR(255) UNIQUE
                );
                CREATE INDEX IF NOT EXISTS idx_node_type ON {TABLE_NODES}(node_type);
            """)
            cur.execute(f"""
                CREATE TABLE IF NOT EXISTS {TABLE_EDGES} (
                    id SERIAL PRIMARY KEY,
                    source_id INT, target_id INT, relation VARCHAR(50),
                    UNIQUE(source_id, target_id, relation)
                );
            """)

    def get_unprocessed_count(self, source_table):
        """获取待处理任务总数"""
        sql = f"""
            SELECT COUNT(*) FROM {source_table} s
            LEFT JOIN {TABLE_RESULT} r ON s.id = r.source_id
            WHERE r.source_id IS NULL
        """
        with self.conn.cursor() as cur:
            cur.execute(sql)
            return cur.fetchone()[0]

    def fetch_unprocessed(self, source_table, limit):
        """核心增量逻辑"""
        sql = f"""
            SELECT s.* FROM {source_table} s
            LEFT JOIN {TABLE_RESULT} r ON s.id = r.source_id
            WHERE r.source_id IS NULL
            ORDER BY s.id ASC LIMIT %s
        """
        with self.conn.cursor(cursor_factory=DictCursor) as cur:
            cur.execute(sql, (limit,))
            return cur.fetchall()

    def save_batch_results(self, results):
        """批量回写结果状态"""
        if not results: return
        sql = f"""
            INSERT INTO {TABLE_RESULT} (source_id, status, extracted_data)
            VALUES %s ON CONFLICT (source_id) DO NOTHING
        """
        with self.conn.cursor() as cur:
            execute_values(cur, sql, results)

    def close(self):
        if self.conn: self.conn.close()