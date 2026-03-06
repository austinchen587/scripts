# build_procurement_type_cache_pname.py
import json
import numpy as np
from pathlib import Path
from sentence_transformers import SentenceTransformer, models

OUTPUT_DIR = Path("D:/code/project/scripts/20251227")
MODEL_PATH = "D:/code/model/text2vec-large-chinese"

OUTPUT_DIR.mkdir(exist_ok=True)

# 简化且更专注的采购类型语义定义
PROCUREMENT_TYPE_PROMPTS = {
    "goods": [
        "采购",
        "购买",
        "购置",
        "物资采购",
        "设备采购",
        "产品采购",
        "商品招标",
        "货物采购",
        "用品购买",
        "办公设备购置"
    ],
    "service": [
        "服务",
        "技术服务",
        "咨询服务",
        "运维服务",
        "培训服务",
        "委托服务",
        "服务外包",
        "维护服务",
        "技术服务招标",
        "专业服务采购"
    ],
    "project": [
        "工程",
        "建设工程",
        "施工工程",
        "安装工程",
        "项目施工",
        "工程项目",
        "工程建设",
        "施工项目",
        "工程安装",
        "建设项目"
    ]
}

def main():
    labels = []
    all_sentences = []

    for typ, sentences in PROCUREMENT_TYPE_PROMPTS.items():
        for sent in sentences:
            labels.append(typ)
            all_sentences.append(sent)

    # 加载模型
    word_emb = models.Transformer(MODEL_PATH)
    pooling = models.Pooling(word_emb.get_word_embedding_dimension())
    model = SentenceTransformer(modules=[word_emb, pooling], device="cuda")

    # 编码并归一化
    embeddings = model.encode(all_sentences, batch_size=32, normalize_embeddings=True).astype(np.float32)

    # 计算每个类别的平均向量作为语义中心
    type_to_vectors = {}
    for typ in PROCUREMENT_TYPE_PROMPTS:
        indices = [i for i, t in enumerate(labels) if t == typ]
        mean_vec = np.mean(embeddings[indices], axis=0)
        type_to_vectors[typ] = mean_vec

    # 保存
    types = list(type_to_vectors.keys())
    vectors = np.stack([type_to_vectors[t] for t in types])

    with open(OUTPUT_DIR / "procurement_types_pname.json", "w", encoding="utf-8") as f:
        json.dump(types, f, ensure_ascii=False)
    np.save(OUTPUT_DIR / "procurement_type_vectors_pname.npy", vectors)
    
    print(f"✅ 语义锚点构建完成")
    print(f"  文件保存到: {OUTPUT_DIR}/procurement_types_pname.json")
    print(f"  每个类型 {len(PROCUREMENT_TYPE_PROMPTS['goods'])} 个示例词汇")

if __name__ == "__main__":
    main()
