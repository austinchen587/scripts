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

# 👉 [新增] 云端大模型 API 配置 (兼容阿里云通义千问、DeepSeek等)
CLOUD_LLM_CONFIG = {
    "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
    "model": "qwen-plus",  # 直接换上这个性价比神机！
    "api_key": "sk-7725072c412d4f4280d091a92772dda1", # 你的真实 API KEY
    "timeout": 300,
    "temperature": 0.1
}

# 应用配置
APP_CONFIG = {
    "batch_size": 30,  # 每次处理的数据量
    "max_retries": 3,  # 最大重试次数
    "log_level": "INFO"
}
