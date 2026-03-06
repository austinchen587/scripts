# config_downfile.py
import os
from pathlib import Path

# 基础路径配置
BASE_DIR = Path("/Users/austinchen587gmail.com/myenv/project/scripts/20251227/20260103")

# 数据库配置
DATABASE_CONFIG = {
    'host': 'localhost',
    'database': 'austinchen587_db',
    'user': 'austinchen587',
    'password': 'austinchen587',
    'port': 5432
}

# 文件保存路径配置
FILE_CONFIG = {
    # 文件保存基础路径
    'base_save_path': BASE_DIR / "source_file",
    
    # 日志保存路径
    'log_dir': BASE_DIR,
    
    # 默认JSON文件路径（可选）
    'default_json_path': BASE_DIR / "classification_results.json"
}

# 下载配置
DOWNLOAD_CONFIG = {
    # 请求超时时间（秒）
    'timeout': 30,
    
    # 重试次数
    'retry_attempts': 3,
    
    # 重试延迟（秒）
    'retry_delay': 2,
    
    # 下载块大小（字节）
    'chunk_size': 8192,
    
    # 支持的文件扩展名
    'supported_extensions': ['.pdf', '.doc', '.docx', '.xls', '.xlsx', '.zip', '.rar', '.txt', '.jpg', '.png']
}

# 日志配置
LOGGING_CONFIG = {
    'level': 'INFO',
    'format': '%(asctime)s - %(levelname)s - %(message)s',
    'date_format': '%Y-%m-%d %H:%M:%S'
}
