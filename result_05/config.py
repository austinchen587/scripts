import os

# 数据库配置
DB_CONFIG = {
    'host': '121.43.77.214',
    'port': 5432,
    'dbname': 'austinchen587_db',
    'user': 'austinchen587',
    'password': 'austinchen587'
}

# 2. 新增云端 Redis 配置
REDIS_CONFIG = {
    'host': '121.43.77.214', 
    'port': 6379,
    'password': 'austinchen587', 
    'decode_responses': True
}

# 表名配置
TABLES = {
    'brand': 'procurement_commodity_brand',
    'sku': 'procurement_commodity_sku',
    'result': 'procurement_commodity_result'
}

# Ollama配置
OLLAMA_CONFIG = {
    "base_url": "http://127.0.0.1:11434",
    "model": "qwen2.5:7b-instruct-q4_K_M",
    "timeout": 120, # 单次请求超时
    "temperature": 0.1
}

# 👉 [新增] 纯文本云端大模型 API 配置
CLOUD_LLM_CONFIG = {
    "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions",
    "model": "qwen3.5-plus",  # 直接换上这个性价比神机！
    "api_key": "sk-7725072c412d4f4280d091a92772dda1", # 你的真实 API KEY
    "timeout": 300,
    "temperature": 0.1
}

# ==========================================
# 【关键修复】批处理策略配置
# 增加了 sleep_between_batches 和 retry_backoff
# ==========================================
BATCH_CONFIG = {
    "batch_size": 10,           # 每组10家
    "winners_per_batch": 3,     # 每组晋级3家
    "sleep_between_batches": 2.0,  # 正常批次间隔休息2秒 (防止Ollama过热)
    "retry_backoff": 5.0        # 报错时等待5秒再重试
}