import logging
import os
import time
from logging.handlers import RotatingFileHandler

# 创建日志目录
LOG_DIR = "logs"
if not os.path.exists(LOG_DIR):
    os.makedirs(LOG_DIR)

def setup_logger():
    # 创建logger对象
    logger = logging.getLogger("ProcurementAI")
    logger.setLevel(logging.INFO)

    # 防止重复添加handler (如果在Jupyter或多次调用时)
    if logger.handlers:
        return logger

    # 1. 定义格式
    # 格式：[时间] [级别] [文件名:行号] 信息
    formatter = logging.Formatter(
        '%(asctime)s [%(levelname)s] [%(filename)s:%(lineno)d] %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    # 2. 文件处理器 (按大小切割，每个文件10MB，保留5个备份)
    # 解决中文乱码问题：encoding='utf-8'
    log_file = os.path.join(LOG_DIR, f"run_{time.strftime('%Y%m%d')}.log")
    file_handler = RotatingFileHandler(log_file, maxBytes=10*1024*1024, backupCount=5, encoding='utf-8')
    file_handler.setFormatter(formatter)
    file_handler.setLevel(logging.INFO)

    # 3. 控制台处理器 (输出到屏幕)
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    console_handler.setLevel(logging.INFO)

    # 4. 添加到logger
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

    return logger

# 初始化单例
logger = setup_logger()