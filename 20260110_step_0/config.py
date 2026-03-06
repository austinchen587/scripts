from pathlib import Path

# 数据库配置
DB_CONFIG = {
    "host": "121.41.76.252",
    "port": 5432,
    "database": "austinchen587_db",
    "user": "austinchen587",
    "password": "austinchen587"
}

# 路径配置：全部放在当前项目目录下
BASE_DIR = Path("D:/code/project/scripts/20260110_step_0")
ATTACH_DIR = BASE_DIR / "attachments"
PDF_DIR = BASE_DIR / "pdfs"
IMG_DIR = BASE_DIR / "images"
VECTOR_DB_DIR = BASE_DIR / "vector_db"

# 创建目录
for d in [ATTACH_DIR, PDF_DIR, IMG_DIR, VECTOR_DB_DIR]:
    d.mkdir(parents=True, exist_ok=True)

# 模型与工具路径
TEXT2VEC_MODEL_PATH = r"D:\code\model\text2vec-large-chinese"
LIBREOFFICE_PATH = r"D:\libreoffice\program\soffice.exe"
POPPLER_PATH = r"D:\Release-25.12.0-0\poppler-25.12.0"
POPPLER_BIN_PATH = r"D:\Release-25.12.0-0\poppler-25.12.0\Library\bin"
OLLAMA_MODEL_DIR = r"D:\ollama_model"

# Ollama 模型名称
OLLAMA_VL_MODEL = "qwen3-vl:4b"
