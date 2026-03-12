# config.py
import os

# ==============================================================================
# 1. 核心路径配置
# ==============================================================================
BASE_DIR = r'D:\code\project\scripts\crawler_04\crawler_0404'

if not os.path.exists(BASE_DIR):
    raise Exception(f"❌ 严重错误：找不到项目根目录 {BASE_DIR}")

# ==============================================================================
# 2. 自动生成子目录
# ==============================================================================
DATA_DIR = os.path.join(BASE_DIR, 'data')
if not os.path.exists(DATA_DIR):
    os.makedirs(DATA_DIR, exist_ok=True)

LOG_DIR = os.path.join(BASE_DIR, 'logs')
if not os.path.exists(LOG_DIR):
    os.makedirs(LOG_DIR, exist_ok=True)

CHROME_DATA_BASE = os.path.join(BASE_DIR, 'browser_data')
if not os.path.exists(CHROME_DATA_BASE):
    os.makedirs(CHROME_DATA_BASE, exist_ok=True)

# ==============================================================================
# 3. 浏览器配置 (补充缺失项)
# ==============================================================================
# [修复] 添加默认地址，防止旧代码引用报错 (虽然现在主要用 browser_manager)
BROWSER_ADDRESS = '127.0.0.1:9222'

# ==============================================================================
# 4. 数据库配置
# ==============================================================================
DB_CONFIG = {
    "dbname": "austinchen587_db",
    "user": "austinchen587",
    "password": "austinchen587",
    "host": "localhost",
    "port": 5432
}

print(f"✅ [Config] 项目根目录: {BASE_DIR}")