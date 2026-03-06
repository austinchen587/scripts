# D:\code\project\scripts\20251227\20251227_version_1\create_vector_cache.py
from pathlib import Path
import json
import numpy as np

# 创建空缓存文件（实际使用时会自动生成）
cache_dir = Path("D:/code/project/scripts/20251227")
cache_dir.mkdir(exist_ok=True)

# 创建基本的类型文件
types = ["goods", "service", "project"]
with open(cache_dir / "procurement_types_pname.json", "w", encoding="utf-8") as f:
    json.dump(types, f, ensure_ascii=False)

# 创建空向量文件（实际模型会填充）
vectors = np.random.randn(len(types), 768).astype(np.float32)
np.save(cache_dir / "procurement_type_vectors_pname.npy", vectors)

print("✅ 向量缓存文件已创建")
