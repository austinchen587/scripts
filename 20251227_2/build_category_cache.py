# D:\code\project\scripts\20251227\build_category_cache.py
import os
import json
import numpy as np
import psycopg2
import pandas as pd
from pathlib import Path
from dotenv import load_dotenv
from sentence_transformers import SentenceTransformer, models

load_dotenv()

OUTPUT_DIR = Path(r"D:\code\project\scripts\20251227")
MODEL_PATH = r"D:\code\model\text2vec-large-chinese"

DB_CONFIG = {
    "host": "localhost",
    "port": 5432,
    "database": "austinchen587_db",
    "user": "austinchen587",
    "password": os.getenv("DB_PASSWORD"),
}

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def load_df(query: str) -> pd.DataFrame:
    with psycopg2.connect(**DB_CONFIG) as conn:
        return pd.read_sql(query, conn)


def build_id_to_node() -> dict:
    df = load_df("SELECT category_id, parent_id, category_name FROM category")
    id_to_node = {}
    for _, r in df.iterrows():
        pid = None if pd.isna(r["parent_id"]) or r["parent_id"] == "0" else str(int(r["parent_id"]))
        id_to_node[str(int(r["category_id"]))] = {"name": r["category_name"], "parent_id": pid}
    return id_to_node


def get_full_path(cat_id: str, id_to_node: dict) -> str:
    parts, current, visited = [], cat_id, set()
    while current and current not in visited and current in id_to_node:
        node = id_to_node[current]
        parts.append(node["name"])
        visited.add(current)
        current = node["parent_id"]
    return " > ".join(reversed(parts))


def main():
    leaf_ids = load_df("SELECT category_id FROM category WHERE is_leaf = true")["category_id"].tolist()
    if not leaf_ids:
        raise ValueError("未找到 is_leaf = true 的品类")

    id_to_node = build_id_to_node()
    paths, valid_ids = [], []
    for cid in leaf_ids:
        cid_str = str(int(cid))
        path = get_full_path(cid_str, id_to_node)
        if path.strip():
            paths.append(path)
            valid_ids.append(cid_str)

    print(f"✅ 构建 {len(valid_ids)} 个叶子品类路径（示例）：")
    for p in paths[:3]:
        print(f"  - {p}")

    print("正在加载 text2vec-large-chinese...")
    word_emb = models.Transformer(MODEL_PATH)
    pooling = models.Pooling(word_emb.get_word_embedding_dimension())
    model = SentenceTransformer(modules=[word_emb, pooling], device="cuda")
    print("✅ 模型加载成功！")

    embeddings = model.encode(paths, batch_size=32, normalize_embeddings=True).astype(np.float32)

    with open(OUTPUT_DIR / "category_ids.json", "w", encoding="utf-8") as f:
        json.dump(valid_ids, f, ensure_ascii=False)
    np.save(OUTPUT_DIR / "category_vectors.npy", embeddings)
    print(f"✅ 向量库已保存至 {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
