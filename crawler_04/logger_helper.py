# logger_helper.py
import logging
import os
from config import BASE_DIR

# 创建日志目录
LOG_DIR = os.path.join(BASE_DIR, 'logs')
if not os.path.exists(LOG_DIR):
    os.makedirs(LOG_DIR)

def get_logger(name="Crawler"):
    logger = logging.getLogger(name)
    if not logger.handlers:
        logger.setLevel(logging.INFO)
        formatter = logging.Formatter('%(asctime)s - [%(levelname)s] - %(message)s', '%H:%M:%S')

        # 控制台输出
        ch = logging.StreamHandler()
        ch.setFormatter(formatter)
        logger.addHandler(ch)

        # 文件输出
        fh = logging.FileHandler(os.path.join(LOG_DIR, 'crawler.log'), encoding='utf-8')
        fh.setFormatter(formatter)
        logger.addHandler(fh)
    return logger

logger = get_logger()