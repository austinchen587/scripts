import os

# 基础路径配置
BASE_DIR = r'D:\code\project\scripts\crawler_04'
DATA_DIR = os.path.join(BASE_DIR, 'data')
if not os.path.exists(DATA_DIR):
    os.makedirs(DATA_DIR)

# 数据库配置 (根据实际情况修改)
DB_CONFIG = {
    "dbname": "austinchen587_db",
    "user": "austinchen587",
    "password": "austinchen587",
    "host": "localhost",
    "port": 5432
}

# 浏览器调试地址
BROWSER_ADDRESS = '127.0.0.1:9222'