import psycopg2
from datetime import datetime

# 你的云服务器公网配置
DB_CONFIG = {
    "host": "121.43.77.214",  # 你的阿里云公网 IP
    "port": 5432,
    "dbname": "austinchen587_db",
    "user": "austinchen587",
    "password": "austinchen587" # 请务必填写你创建用户时设的密码
}

def test_remote_insert():
    conn = None
    try:
        print("🔍 正在尝试跨越公网连接 PostgreSQL 18...")
        conn = psycopg2.connect(**DB_CONFIG)
        cur = conn.cursor()

        # 模拟插入一条测试品牌数据
        print("📝 正在写入测试数据...")
        sql = """
            INSERT INTO procurement_commodity_brand (procurement_id, item_name, key_word)
            VALUES (%s, %s, %s) RETURNING id;
        """
        cur.execute(sql, ("TEST_001", "联调测试商品", "MacBook M3"))
        
        new_id = cur.fetchone()[0]
        conn.commit()
        
        print(f"✅ 写入成功！产生的新 ID 是: {new_id}")
        print("🎉 恭喜，你的本地机器已具备远程交单能力！")

    except Exception as e:
        print(f"❌ 连接或写入失败: {e}")
        print("\n💡 排查建议：")
        print("1. 检查阿里云安全组是否放行了 5432 端口？")
        print("2. 检查 psql 配置是否允许远程连接 (postgresql.conf 中的 listen_addresses)？")
    finally:
        if conn: conn.close()

if __name__ == "__main__":
    test_remote_insert()