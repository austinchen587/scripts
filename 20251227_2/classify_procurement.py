# D:\code\project\scripts\20251227\classify_procurement.py
import sys
from pathlib import Path
from datetime import datetime
import json
import numpy as np
from tqdm import tqdm
from sklearn.metrics.pairwise import cosine_similarity
from sentence_transformers import SentenceTransformer, models

sys.path.append(str(Path(__file__).parent.parent.parent))  # 指向 project 根目录

from config.settings import CONFIDENCE_THRESHOLD, MODEL_PATH
from src.db.connection import get_connection

TEST_MODE = True
TEST_LIMIT = 100
OUTPUT_DIR = Path(r"D:\code\project\scripts\20251227")
OUTPUT_DIR.mkdir(exist_ok=True)

_text_model = None
_category_ids = None
_category_vectors = None
_brand_keyword_map = None


def get_text_model():
    global _text_model
    if _text_model is None:
        print("✅ 加载 text2vec-large-chinese 模型...")
        word_emb = models.Transformer(MODEL_PATH)
        pooling = models.Pooling(word_emb.get_word_embedding_dimension())
        _text_model = SentenceTransformer(modules=[word_emb, pooling], device="cuda")
    return _text_model


def load_category_cache():
    global _category_ids, _category_vectors
    if _category_ids is None:
        cache_dir = OUTPUT_DIR
        with open(cache_dir / "category_ids.json", "r", encoding="utf-8") as f:
            _category_ids = json.load(f)
        _category_vectors = np.load(cache_dir / "category_vectors.npy")


def get_brand_keyword_map():
    global _brand_keyword_map
    if _brand_keyword_map is None:
        cache_path = OUTPUT_DIR / "brand_keyword_map.json"
        with open(cache_path, "r", encoding="utf-8") as f:
            _brand_keyword_map = json.load(f)
    return _brand_keyword_map


def build_input_text(project_name: str, commodity_names) -> str:
    parts = []
    if project_name and project_name.strip():
        parts.append(project_name.strip())
    if commodity_names:
        for item in commodity_names:
            if item and item.strip():
                parts.append(item.strip())
    return " ".join(parts)


def extract_brands_from_text(text: str, brand_map: dict) -> set:
    text_lower = text.lower()
    matched = set()
    for keyword in brand_map.keys():
        if keyword in text_lower:
            matched.add(keyword)
    return matched


def classify_record(text: str):
    load_category_cache()
    model = get_text_model()
    emb = model.encode([text], normalize_embeddings=True)
    sims = cosine_similarity(emb, _category_vectors)[0]

    brand_map = get_brand_keyword_map()
    matched_brands = extract_brands_from_text(text, brand_map)

    allowed_cats = set()
    for brand in matched_brands:
        allowed_cats.update(brand_map[brand])

    if allowed_cats:
        for idx, cat_id in enumerate(_category_ids):
            if int(cat_id) in allowed_cats and sims[idx] >= 0.65:
                return int(cat_id), float(sims[idx])

    best_idx = int(np.argmax(sims))
    best_score = sims[best_idx]
    if best_score >= CONFIDENCE_THRESHOLD:
        return int(_category_ids[best_idx]), float(best_score)
    
    return None, 0.0


def main():
    load_category_cache()
    print(f"✅ 加载 {_category_vectors.shape[0]} 个叶子品类")

    conn = get_connection()
    with conn.cursor() as cur:
        if TEST_MODE:
            query = """
            SELECT id, project_name, commodity_names
            FROM procurement_emall
            WHERE (project_name IS NOT NULL OR commodity_names IS NOT NULL)
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

    log_file = OUTPUT_DIR / f"classify_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jsonl"
    with open(log_file, "w", encoding="utf-8") as log_f:
        for row in tqdm(records, desc="分类进度"):
            record_id = row[0]
            project_name = row[1]
            commodity_names = row[2] or []
            input_text = build_input_text(project_name, commodity_names)
            if not input_text.strip():
                continue

            pred_id, conf = classify_record(input_text)
            requires_review = pred_id is None

            result = {
                "record_id": record_id,
                "input_text": input_text,
                "predicted_category_id": pred_id,
                "confidence_score": round(conf, 4),
                "requires_manual_review": requires_review,
                "timestamp": datetime.now().isoformat()
            }
            log_f.write(json.dumps(result, ensure_ascii=False) + "\n")

    print(f"\n✅ 完成 {len(records)} 条记录分类，日志已保存至：{log_file}")


if __name__ == "__main__":
    main()
