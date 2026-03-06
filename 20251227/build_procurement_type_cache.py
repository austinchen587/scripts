# build_procurement_type_cache.py
import json
import numpy as np
from pathlib import Path
from sentence_transformers import SentenceTransformer, models

OUTPUT_DIR = Path("D:/code/project/scripts/20251227")
MODEL_PATH = "D:/code/model/text2vec-large-chinese"

OUTPUT_DIR.mkdir(exist_ok=True)

# 采购类型语义定义
PROCUREMENT_TYPE_PROMPTS = {
    "goods": [
        "这是一项实物商品的采购，目的是获得有形物品的所有权，例如设备、耗材、工具、材料等。",
        "采购内容是具体的物理产品，交付物是可触摸、可清点的货物，不涉及施工或长期服务。",
        "项目以购买标准化或定制化产品为主，重点关注产品规格、品牌、数量、检测报告和质保。"
    ],
    "service": [
        "这是一项无形服务的采购，目的是获取人力、知识或系统支持，例如咨询、运维、培训、设计、监理等。",
        "采购内容是人的劳动或专业能力输出，交付物是报告、方案、代码、活动执行或持续性保障。",
        "项目不涉及实物交付或工程建设，核心是完成某项任务或提供某种能力支持。"
    ],
    "project": [
        "这是一项工程建设或安装施工类采购，目的是完成一个实体设施的建造、改造或安装。",
        "采购内容包含现场作业、施工图纸、工期要求、验收标准，通常涉及土建、装修、机电或系统集成。",
        "项目强调‘做工程’，需供应商组织施工队伍、进行现场作业，并按期交付一个完整工程成果。"
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

    with open(OUTPUT_DIR / "procurement_types.json", "w", encoding="utf-8") as f:
        json.dump(types, f, ensure_ascii=False)
    np.save(OUTPUT_DIR / "procurement_type_vectors.npy", vectors)

if __name__ == "__main__":
    main()
