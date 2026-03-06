# D:\code\project\scripts\classify_procurement.py
import sys
import os
from pathlib import Path
from datetime import datetime
import json
import numpy as np
from sklearn.metrics.pairwise import cosine_similarity
from sentence_transformers import SentenceTransformer, models

# 将 project 根目录加入 Python 路径
sys.path.append(str(Path(__file__).parent.parent))

from config.settings import (
    CONFIDENCE_THRESHOLD,
    MODEL_PATH,
)
from src.db.connection import get_connection
from src.text.input_builder import build_input_text
from src.model.embedding_loader import load_category_embeddings

# —— 配置 ——
TEST_MODE = True
TEST_LIMIT = 40  # 小样本数量
LOG_DIR = Path(r"D:\code\project\logs")
LOG_DIR.mkdir(exist_ok=True)
LOG_FILE = LOG_DIR / f"classify_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jsonl"


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


# —— 主分类函数 ——
def classify_text(text: str, category_ids, category_vectors):
    model = get_text_model()
    emb = model.encode([text], normalize_embeddings=True)
    scores = cosine_similarity(emb, category_vectors)[0]
    best_idx = int(np.argmax(scores))
    return category_ids[best_idx], float(scores[best_idx])


# —— 主流程 ——
def main():
    # 1. 加载品类向量库
    category_ids, category_vectors = load_category_embeddings()
    print(f"✅ 加载 {len(category_ids)} 个叶子品类")

    # 2. 查询数据
    conn = get_connection()
    with conn.cursor() as cur:
        if TEST_MODE:
            query = """
            SELECT id, project_name, commodity_names, parameter_requirements
            FROM procurement_emall
            WHERE project_name IS NOT NULL 
               OR commodity_names IS NOT NULL 
               OR parameter_requirements IS NOT NULL
            ORDER BY id
            LIMIT %s
            """
            cur.execute(query, (TEST_LIMIT,))
        else:
            # 未来可替换为增量查询
            query = """
            SELECT id, project_name, commodity_names, parameter_requirements
            FROM procurement_emall
            WHERE created_at > NOW() - INTERVAL '3 hours'
            """
            cur.execute(query)
        
        records = cur.fetchall()
    
    # 3. 分类并写日志
    with open(LOG_FILE, "w", encoding="utf-8") as log_f:
        for row in records:
            record_id = row[0]
            record = {
                "project_name": row[1],
                "commodity_names": row[2] or [],
                "parameter_requirements": row[3] or [],
            }
            input_text = build_input_text(record)
            if not input_text.strip():
                print(f"⚠️ 跳过空文本记录 {record_id}")
                continue

            # 分类
            pred_id, conf = classify_text(input_text, category_ids, category_vectors)
            requires_review = conf < CONFIDENCE_THRESHOLD

            result = {
                "record_id": record_id,
                "input_text": input_text,
                "predicted_category_id": pred_id,
                "confidence_score": round(conf, 4),
                "used_attachment": False,       # 暂时禁用
                "requires_manual_review": requires_review,
                "timestamp": datetime.now().isoformat()
            }

            # 写入 JSONL 日志（一行一个 JSON）
            log_f.write(json.dumps(result, ensure_ascii=False) + "\n")
            print(f"✅ {record_id}: {pred_id} (conf={conf:.4f})")

    conn.close()
    print(f"\n✅ 完成 {len(records)} 条记录分类，日志已保存至：{LOG_FILE}")


if __name__ == "__main__":
    main()