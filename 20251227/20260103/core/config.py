# config.py
import os
from pathlib import Path
import sys

# 添加上级目录到路径，以便导入config_downfile
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from config_downfile import DATABASE_CONFIG, FILE_CONFIG, DOWNLOAD_CONFIG, LOGGING_CONFIG, BASE_DIR
except ImportError:
    # 备用配置
    BASE_DIR = Path("/Users/austinchen587gmail.com/myenv/project/scripts/20251227/20260103")
    
    DATABASE_CONFIG = {
        'host': 'localhost',
        'database': 'austinchen587_db',
        'user': 'austinchen587',
        'password': 'austinchen587',
        'port': 5432
    }
    
    FILE_CONFIG = {
        'base_save_path': BASE_DIR / "source_file",
        'log_dir': BASE_DIR,
        'default_json_path': BASE_DIR / "classification_results.json"
    }

# 模型配置
MODEL_CONFIG = {
    'text_model': 'qwen2.5:7b-instruct-q4_K_M',
    'vision_model': 'qwen3-vl:4b',
    'temperature': 0.1,
    'max_tokens': 2048
}

# 日志配置
LOG_CONFIG = {
    'log_file': BASE_DIR / 'core_engine.log',
    'level': 'INFO'
}
