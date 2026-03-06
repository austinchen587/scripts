# D:\code\project\scripts\build_brand_vector_db.py
import os
import json
import numpy as np
import psycopg2
import pandas as pd
from pathlib import Path
from dotenv import load_dotenv
from sentence_transformers import SentenceTransformer, models

load_dotenv()

PROJECT_ROOT = Path(r"D:\code\project")
CACHE_DIR = PROJECT_ROOT / "data" / "cache"
MODEL_PATH = r"D:\code\model\text2vec-large-chinese"

DB_CONFIG = {
    "host": "localhost",
    "port": 5432,
    "database": "austinchen587_db",
    "user": "austinchen587",
    "password": os.getenv("DB_PASSWORD"),
}
CACHE_DIR.mkdir(parents=True, exist_ok=True)


def load_brand_df() -> pd.DataFrame:
    with psycopg2.connect(**DB_CONFIG) as conn:
        query = """
        SELECT id, full_name, name, ch_name, en_name, category_id
        FROM brand
        WHERE category_id IS NOT NULL
        """
        return pd.read_sql(query, conn)


def build_brand_text(row) -> str:
    fields = [row["full_name"], row["name"], row["ch_name"], row["en_name"]]
    unique_texts = list(dict.fromkeys([str(f).strip() for f in fields if f and str(f).strip()]))
    return " ".join(unique_texts)


def load_text2vec_model(model_path: str):
    word_emb = models.Transformer(model_path)
    pooling = models.Pooling(word_emb.get_word_embedding_dimension())
    return SentenceTransformer(modules=[word_emb, pooling], device="cuda")


def main():
    print("✅ 加载 brand 表...")
    df = load_brand_df()
    print(f"✅ 共 {len(df)} 条品牌记录")

    brand_texts, brand_ids, category_ids = [], [], []
    for _, row in df.iterrows():
        text = build_brand_text(row)
        if text.strip():
            brand_texts.append(text)
            brand_ids.append(int(row["id"]))
            category_ids.append(row["category_id"])

    print(f"✅ 构建 {len(brand_texts)} 个有效品牌文本（示例）：")
    for t in brand_texts[:3]:
        print(f"  - {t}")

    print("🔄 加载模型...")
    model = load_text2vec_model(MODEL_PATH)
    print("✅ 模型加载成功！")

    # 👇 关键：启用进度条（内部已多线程）
    print("🔄 向量化（带进度条，自动多线程）...")
    embeddings = model.encode(
        brand_texts,
        batch_size=32,
        normalize_embeddings=True,
        show_progress_bar=True,   # 显示 tqdm
        device="cuda"
    ).astype(np.float32)

    print("💾 保存...")
    with open(CACHE_DIR / "brand_ids.json", "w", encoding="utf-8") as f:
        json.dump(brand_ids, f, ensure_ascii=False)
    with open(CACHE_DIR / "brand_category_ids.json", "w", encoding="utf-8") as f:
        json.dump(category_ids, f, ensure_ascii=False)
    np.save(CACHE_DIR / "brand_vectors.npy", embeddings)

    print(f"✅ 完成！向量 shape: {embeddings.shape}")


if __name__ == "__main__":
    main()