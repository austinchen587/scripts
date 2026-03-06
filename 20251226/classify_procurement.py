# D:\code\project\scripts\classify_procurement.py
import sys
import os
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))

import json
import numpy as np
from sklearn.metrics.pairwise import cosine_similarity
from sentence_transformers import SentenceTransformer, models
from config.settings import (
    CONFIDENCE_THRESHOLD,
    ATTACHMENT_HINTS,
    MODEL_PATH,
    ATTACHMENT_TEMP_DIR
)
from src.db.connection import get_connection
from src.text.input_builder import build_input_text
from src.text.attachment_detector import contains_attachment_hint
from src.model.embedding_loader import load_category_embeddings
from src.attachment.downloader import download_file
from src.attachment.extractor import extract_text

# —— 小样本测试模式（设为 None 则处理全表）——
TEST_RECORD_IDS = None  # 例如：[1001, 1005, 1023]

# —— 模型懒加载 ——
_text_model = None
def get_text_model():
    global _text_model
    if _text_model is None:
        print("✅ 加载 text2vec-large-chinese 模型...")
        word_emb = models.Transformer(MODEL_PATH)
        pooling = models.Pooling(word_emb.get_word_embedding_dimension())
        _text_model = SentenceTransformer(modules=[word_emb, pooling], device="cuda")
    return _text_model

# —— 向量分类 ——
def classify_with_vectors(text: str, category_ids, category_vectors):
    model = get_text_model()
    emb = model.encode([text], normalize_embeddings=True)
    scores = cosine_similarity(emb, category_vectors)[0]
    best_idx = int(np.argmax(scores))
    return category_ids[best_idx], float(scores[best_idx])

# —— 附件增强 ——
def enhance_with_attachment(record, base_text, category_ids, category_vectors):
    urls = []
    if record.get("related_links"):
        urls.extend(record["related_links"])
    if record.get("download_files"):
        urls.extend(record["download_files"])
    
    ATTACHMENT_TEMP_DIR.mkdir(parents=True, exist_ok=True)
    extra_text = ""
    used = False
    
    for url in urls:
        if not url or not url.strip():
            continue
        filepath = download_file(url, ATTACHMENT_TEMP_DIR)
        if filepath and filepath.exists():
            text = extract_text(filepath)
            if text.strip():
                extra_text += " " + text
                used = True
            filepath.unlink()  # 清理临时文件
    
    if extra_text.strip():
        enhanced_text = (base_text + " " + extra_text).strip()
        cat_id, conf = classify_with_vectors(enhanced_text, category_ids, category_vectors)
        return cat_id, conf, True
    return None, None, False

# —— 主流程 ——
def main():
    # 1. 加载品类向量库
    category_ids, category_vectors = load_category_embeddings()
    print(f"✅ 加载 {len(category_ids)} 个叶子品类")

    # 2. 构建查询
    conn = get_connection()
    with conn.cursor() as cur:
        if TEST_RECORD_IDS:
            placeholders = ','.join(['%s'] * len(TEST_RECORD_IDS))
            query = f"""
            SELECT id, project_name, commodity_names, parameter_requirements, related_links, download_files
            FROM procurement_emall
            WHERE id IN ({placeholders})
            """
            cur.execute(query, TEST_RECORD_IDS)
        else:
            # 可扩展：WHERE created_at > last_run_time
            query = """
            SELECT id, project_name, commodity_names, parameter_requirements, related_links, download_files
            FROM procurement_emall
            ORDER BY id
            LIMIT 20  -- 限制全量测试条数
            """
            cur.execute(query)
        
        records = cur.fetchall()
    
    # 3. 处理每条记录
    results = []
    for row in records:
        record = {
            "id": row[0],
            "project_name": row[1],
            "commodity_names": row[2] or [],
            "parameter_requirements": row[3] or [],
            "related_links": row[4] or [],
            "download_files": row[5] or [],
        }
        base_text = build_input_text(record)
        if not base_text.strip():
            print(f"⚠️ 跳过空文本记录 {record['id']}")
            continue

        # 初始分类
        pred_id, conf = classify_with_vectors(base_text, category_ids, category_vectors)
        requires_review = conf < CONFIDENCE_THRESHOLD
        used_attachment = False

        # 附件增强（仅当需要人工审核 + 含提示）
        if requires_review and contains_attachment_hint(base_text):
            new_id, new_conf, used = enhance_with_attachment(record, base_text, category_ids, category_vectors)
            if used:
                used_attachment = True
                if new_conf >= CONFIDENCE_THRESHOLD:
                    pred_id, conf = new_id, new_conf
                    requires_review = False

        result = {
            "record_id": record["id"],
            "input_text": base_text[:100] + ("..." if len(base_text) > 100 else ""),
            "predicted_category_id": pred_id,
            "confidence_score": round(conf, 4),
            "used_attachment": used_attachment,
            "requires_manual_review": requires_review,
        }
        results.append(result)
        print(json.dumps(result, ensure_ascii=False, indent=2))

    conn.close()
    print(f"\n✅ 完成 {len(results)} 条记录分类")

if __name__ == "__main__":
    main()