# D:\code\project\scripts\classify_procurement.py
import sys
from pathlib import Path
from datetime import datetime
import json
import numpy as np
from tqdm import tqdm  # 👈 新增
from sklearn.metrics.pairwise import cosine_similarity
from sentence_transformers import SentenceTransformer, models

sys.path.append(str(Path(__file__).parent.parent))

from config.settings import CONFIDENCE_THRESHOLD, MODEL_PATH
from src.db.connection import get_connection
from src.model.embedding_loader import load_category_embeddings

TEST_MODE = True
TEST_LIMIT = 100
LOG_DIR = Path(r"D:\code\project\logs")
LOG_DIR.mkdir(exist_ok=True)
LOG_FILE = LOG_DIR / f"classify_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jsonl"

_text_model = None
def get_text_model():
    global _text_model
    if _text_model is None:
        print("✅ 加载 text2vec-large-chinese 模型...")
        word_emb = models.Transformer(MODEL_PATH)
        pooling = models.Pooling(word_emb.get_word_embedding_dimension())
        _text_model = SentenceTransformer(modules=[word_emb, pooling], device="cuda")
    return _text_model

def load_brand_embeddings():
    cache_dir = Path(r"D:\code\project\data\cache")
    brand_ids = json.load(open(cache_dir / "brand_ids.json", "r", encoding="utf-8"))
    brand_category_ids = json.load(open(cache_dir / "brand_category_ids.json", "r", encoding="utf-8"))
    brand_vectors = np.load(cache_dir / "brand_vectors.npy")
    return brand_ids, brand_category_ids, brand_vectors

def build_input_text(project_name: str, commodity_names) -> str:
    parts = []
    if project_name and project_name.strip():
        parts.append(project_name.strip())
    if commodity_names:
        for item in commodity_names:
            if item and item.strip():
                parts.append(item.strip())
    return " ".join(parts)

def classify_text(text: str, category_ids, category_vectors, brand_category_ids, brand_vectors):
    model = get_text_model()
    emb = model.encode([text], normalize_embeddings=True)
    cat_scores = cosine_similarity(emb, category_vectors)[0]
    brand_scores = cosine_similarity(emb, brand_vectors)[0]
    best_brand_score = brand_scores.max()
    if best_brand_score > 0.65:
        best_brand_idx = int(brand_scores.argmax())
        brand_cat_id = brand_category_ids[best_brand_idx]
        if brand_cat_id in category_ids:
            cat_idx = category_ids.index(brand_cat_id)
            cat_scores[cat_idx] *= 1.2
    best_idx = int(np.argmax(cat_scores))
    return category_ids[best_idx], float(cat_scores[best_idx])

def main():
    category_ids, category_vectors = load_category_embeddings()
    _, brand_category_ids, brand_vectors = load_brand_embeddings()
    print(f"✅ 加载 {len(category_ids)} 个叶子品类")
    print(f"✅ 加载 {len(brand_category_ids)} 个品牌向量")

    conn = get_connection()
    with conn.cursor() as cur:
        if TEST_MODE:
            query = """
            SELECT id, project_name, commodity_names
            FROM procurement_emall
            WHERE project_name IS NOT NULL OR commodity_names IS NOT NULL
            ORDER BY id
            LIMIT %s
            """
            cur.execute(query, (TEST_LIMIT,))
        else:
            query = """
            SELECT id, project_name, commodity_names
            FROM procurement_emall
            WHERE created_at > NOW() - INTERVAL '3 hours'
            """
            cur.execute(query)
        records = cur.fetchall()
    conn.close()

    # 👇 关键：用 tqdm 包裹 records
    with open(LOG_FILE, "w", encoding="utf-8") as log_f:
        for row in tqdm(records, desc="分类进度"):
            record_id = row[0]
            project_name = row[1]
            commodity_names = row[2] or []
            input_text = build_input_text(project_name, commodity_names)
            if not input_text.strip():
                continue
            pred_id, conf = classify_text(input_text, category_ids, category_vectors, brand_category_ids, brand_vectors)
            requires_review = conf < CONFIDENCE_THRESHOLD
            result = {
                "record_id": record_id,
                "input_text": input_text,
                "predicted_category_id": pred_id,
                "confidence_score": round(conf, 4),
                "used_attachment": False,
                "requires_manual_review": requires_review,
                "timestamp": datetime.now().isoformat()
            }
            log_f.write(json.dumps(result, ensure_ascii=False) + "\n")

    print(f"\n✅ 完成 {len(records)} 条记录分类，日志已保存至：{LOG_FILE}")

if __name__ == "__main__":
    main()