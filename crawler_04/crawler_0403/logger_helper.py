# logger_helper.py
import logging
import os
import sys
from config import LOG_DIR  # 从 config 中直接读取日志目录

# 确保日志目录存在
if not os.path.exists(LOG_DIR):
    os.makedirs(LOG_DIR)

def get_logger(name="Crawler"):
    logger = logging.getLogger(name)
    
    # 防止重复添加 Handler 导致日志重复打印
    if not logger.handlers:
        logger.setLevel(logging.INFO)
        
        # 格式：时间 - 级别 - 消息
        formatter = logging.Formatter('%(asctime)s - [%(levelname)s] - %(message)s', '%H:%M:%S')

        # 1. 控制台输出 (Console)
        ch = logging.StreamHandler(sys.stdout)
        ch.setFormatter(formatter)
        logger.addHandler(ch)

        # 2. 文件输出 (File)
        log_file_path = os.path.join(LOG_DIR, 'crawler.log')
        fh = logging.FileHandler(log_file_path, encoding='utf-8')
        fh.setFormatter(formatter)
        logger.addHandler(fh)
        
    return logger

# 初始化单例
logger = get_logger()