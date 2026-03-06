"""
配置文件
"""

# 数据库配置
DB_CONFIG = {
    "host": "localhost",
    "database": "austinchen587_db",
    "user": "austinchen587",
    "password": "austinchen587",
    "port": 5432,
    "connect_timeout": 10
}

# Ollama配置
OLLAMA_CONFIG = {
    "base_url": "http://127.0.0.1:11434",
    "model": "qwen2.5:7b-instruct-q4_K_M",
    "timeout": 60
}

# 应用配置
APP_CONFIG = {
    "batch_size": 50,  # 每次处理的数据量
    "max_retries": 3,  # 最大重试次数
    "log_level": "INFO"
}
