# config.py
import os


# =========================================================
# 关键修复：强制设置不使用代理的环境变量
# 这必须在导入其他网络库(requests, ollama)之前设置
# =========================================================
os.environ['NO_PROXY'] = 'localhost,127.0.0.1,0.0.0.0,::1'
os.environ['no_proxy'] = 'localhost,127.0.0.1,0.0.0.0,::1'

# 数据库
DB_CONFIG = {
    "host": "localhost",
    "port": 5432,
    "database": "austinchen587_db",
    "user": "austinchen587",
    "password": "austinchen587"
}

# ========== Windows路径配置 ==========
# 项目根目录
PROJECT_ROOT = r"D:\code\project\scripts\20260111_step_2"
DOWNLOAD_DIR = os.path.join(PROJECT_ROOT, "downloads")
OUTPUT_DIR = os.path.join(PROJECT_ROOT, "outputs")
VECTOR_DB_PATH = r"D:\code\project\scripts\20260110_step_0\vector_db"

# 模型路径 - 根据您提供的信息，我猜测您是把text2vec模型也放在了ollama_model目录
TEXT2VEC_MODEL_PATH = r"D:\code\model\text2vec-large-chinese"

# LibreOffice路径
LIBREOFFICE_PATH = r"D:\libreoffice\program\soffice.exe"

# Poppler路径
POPPLER_PATH = r"D:\Release-25.12.0-0\poppler-25.12.0"
POPPLER_BIN_PATH = r"D:\Release-25.12.0-0\poppler-25.12.0\Library\bin"
# ========== 关键修复：强制设置环境变量 ==========
os.environ['PATH'] = f"{POPPLER_BIN_PATH};{os.environ.get('PATH', '')}"

# ========== LLM配置 ==========
OLLAMA_URL = "http://localhost:11434/api/generate"
LLM_MODEL = "qwen3:8b"  # 用于文本处理的模型
VISION_MODEL = "qwen3-vl:4b"  # 用于图片理解的模型 - 新增

# ========== RAG配置 ==========
TOP_K_CASES = 3

# ========== 创建必要的目录 ==========
os.makedirs(DOWNLOAD_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)

# ========== 环境变量设置 ==========
# 修复tokenizers并行性警告
os.environ["TOKENIZERS_PARALLELISM"] = "false"
