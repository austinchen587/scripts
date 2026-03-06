# utils.py
import json
import logging
import logging.config
from pathlib import Path
from config import LOG_CONFIG

def setup_logging():
    """配置日志"""
    log_file = Path(LOG_CONFIG['log_file'])
    log_file.parent.mkdir(parents=True, exist_ok=True)
    
    logging.basicConfig(
        level=LOG_CONFIG['level'],
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_file, encoding='utf-8'),
            logging.StreamHandler()
        ]
    )

def load_json_file(file_path):
    """加载JSON文件"""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        logging.error(f"JSON文件加载失败 {file_path}: {e}")
        return None

def save_results(results, output_path):
    """保存结果到JSON文件"""
    try:
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
        logging.info(f"结果已保存到: {output_path}")
        return True
    except Exception as e:
        logging.error(f"结果保存失败 {output_path}: {e}")
        return False
