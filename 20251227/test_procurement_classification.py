# test_procurement_classification.py
import sys
import json
import random
import numpy as np
from pathlib import Path
from tqdm import tqdm
from collections import defaultdict
from sklearn.metrics.pairwise import cosine_similarity
from sentence_transformers import SentenceTransformer, models

sys.path.append(str(Path(__file__).parent.parent.parent))

from config.settings import MODEL_PATH
from src.db.connection import get_connection

# 配置
OUTPUT_DIR = Path("D:/code/project/scripts/20251227")
TARGET_COVERAGE = 0.95  # 95%覆盖目标
THRESHOLD = 0.7  # 置信度阈值
SAMPLE_SIZE = 100  # 随机样本数

_text_model = None
_procurement_types = None
_procurement_type_vectors = None

def get_text_model():
    global _text_model
    if _text_model is None:
        word_emb = models.Transformer(MODEL_PATH)
        pooling = models.Pooling(word_emb.get_word_embedding_dimension())
        _text_model = SentenceTransformer(modules=[word_emb, pooling], device="cuda")
    return _text_model

def load_procurement_type_cache():
    global _procurement_types, _procurement_type_vectors
    if _procurement_types is None:
        with open(OUTPUT_DIR / "procurement_types.json", "r", encoding="utf-8") as f:
            _procurement_types = json.load(f)
        _procurement_type_vectors = np.load(OUTPUT_DIR / "procurement_type_vectors.npy")

def build_input_text(project_name, commodity_names, parameter_requirements) -> str:
    """拼接原始字段作为分类输入"""
    parts = []

    if project_name and isinstance(project_name, str):
        parts.append(project_name.strip())

    if commodity_names and isinstance(commodity_names, list):
        for item in commodity_names:
            if item and isinstance(item, str):
                parts.append(item.strip())

    if parameter_requirements and isinstance(parameter_requirements, list):
        for item in parameter_requirements:
            if item and isinstance(item, str):
                s = item.strip()
                if s.startswith('"') and s.endswith('"'):
                    s = s[1:-1]
                parts.append(s)

    raw_text = " ".join([p for p in parts if p])
    if not raw_text:
        return ""
    
    return raw_text

def classify_procurement_type(text: str) -> tuple[str, float]:
    """返回采购类型和置信度"""
    if not text.strip():
        return "unknown", 0.0

    load_procurement_type_cache()
    model = get_text_model()
    emb = model.encode([text], normalize_embeddings=True)
    sims = cosine_similarity(emb, _procurement_type_vectors)[0]
    best_idx = int(np.argmax(sims))
    return _procurement_types[best_idx], float(sims[best_idx])

def main():
    print("=" * 60)
    print("📊 采购记录分类测试")
    print(f"测试配置：{SAMPLE_SIZE}个随机样本，置信度阈值={THRESHOLD}")
    print("目标：阈值>=0.7 覆盖 {:.0f}%+ 的记录".format(TARGET_COVERAGE * 100))
    print("=" * 60)
    
    # 加载模型和缓存
    get_text_model()
    load_procurement_type_cache()
    
    # 从数据库读取采购记录
    conn = get_connection()
    with conn.cursor() as cur:
        # 获取总记录数
        cur.execute("SELECT COUNT(*) FROM procurement_emall")
        total_count = cur.fetchone()[0]
        
        print(f"数据库中共有 {total_count:,} 条采购记录")
        
        # 获取所有ID，随机选择
        cur.execute("SELECT id FROM procurement_emall ORDER BY RANDOM() LIMIT %s", (SAMPLE_SIZE,))
        sample_ids = [row[0] for row in cur.fetchall()]
        
        # 获取样本的详细信息
        cur.execute("""
            SELECT id, project_name, commodity_names, parameter_requirements
            FROM procurement_emall
            WHERE id = ANY(%s)
            ORDER BY id
        """, (sample_ids,))
        records = cur.fetchall()
    conn.close()
    
    print(f"\n✅ 随机选择了 {len(records)} 个样本")
    
    # 测试结果统计
    high_confidence_count = 0
    low_confidence_count = 0
    empty_text_count = 0
    
    # 详细日志存储
    detailed_logs = []
    confidence_values = []
    
    print("\n" + "-" * 100)
    print("📝 详细分类日志:")
    print("-" * 100)
    
    # 逐条分类测试
    for idx, row in enumerate(tqdm(records, desc="测试进度", ncols=80)):
        record_id = row[0]
        project_name = row[1]
        commodity_names = row[2] or []
        parameter_requirements = row[3] or []
        
        # 构建输入文本
        input_text = build_input_text(project_name, commodity_names, parameter_requirements)
        
        if not input_text.strip():
            empty_text_count += 1
            log_entry = f"🔴 样本 {idx+1:3d} (ID:{record_id}): 无有效文本内容"
            detailed_logs.append(log_entry)
            print(log_entry)
            continue
        
        # 进行分类
        p_type, p_conf = classify_procurement_type(input_text)
        confidence_values.append(p_conf)
        
        # 判断是否达到阈值
        meets_threshold = p_conf >= THRESHOLD
        
        # 计数
        if meets_threshold:
            high_confidence_count += 1
            confidence_marker = "✅"
        else:
            low_confidence_count += 1
            confidence_marker = "⚠️ "
        
        # 构建日志条目
        input_preview = input_text[:80] + "..." if len(input_text) > 80 else input_text
        
        log_entry = f"{confidence_marker} 样本 {idx+1:3d} (ID:{record_id}):"
        log_entry += f" 类型={p_type:<8}"
        log_entry += f" 置信度={p_conf:.4f}"
        log_entry += f" {'🔺达标' if meets_threshold else '🔻未达标'}"
        log_entry += f"\n   输入预览: {input_preview}"
        
        detailed_logs.append(log_entry)
        print(log_entry)
    
    print("\n" + "=" * 100)
    print("📊 测试结果汇总:")
    print("=" * 100)
    
    valid_samples = len(records) - empty_text_count
    
    if valid_samples > 0:
        # 计算覆盖率
        coverage_rate = high_confidence_count / valid_samples
        avg_confidence = np.mean(confidence_values) if confidence_values else 0
        
        print(f"📈 总样本数: {len(records)}")
        print(f"📄 有效样本数（有文本内容）: {valid_samples}")
        print(f"⚪ 空文本样本数: {empty_text_count}")
        print(f"")
        print(f"🟢 高置信度样本（>= {THRESHOLD}）: {high_confidence_count}")
        print(f"🟡 低置信度样本（< {THRESHOLD}）: {low_confidence_count}")
        print(f"")
        print(f"📊 覆盖率: {high_confidence_count}/{valid_samples} = {coverage_rate:.2%}")
        print(f"📊 平均置信度: {avg_confidence:.4f}")
        print(f"📈 置信度范围: {min(confidence_values):.4f} - {max(confidence_values):.4f}")
        print(f"")
        print(f"🎯 目标覆盖率: {TARGET_COVERAGE:.0%}")
        print(f"🏆 测试结果: {'✅ 达标' if coverage_rate >= TARGET_COVERAGE else '❌ 未达标'}")
        
        # 置信度分布
        print(f"\n📊 置信度分布:")
        bins = [(0, 0.3), (0.3, 0.5), (0.5, 0.7), (0.7, 0.85), (0.85, 1.0)]
        for low, high in bins:
            count = sum(1 for conf in confidence_values if low <= conf < high)
            pct = count / len(confidence_values) if confidence_values else 0
            bar = "█" * int(pct * 50)
            print(f"  {low:.2f}-{high:.2f}: {count:3d} 个 ({pct:.1%}) {bar}")
        
        # 保存详细结果到文件
        log_file = Path("procurement_test_log.txt")
        with open(log_file, "w", encoding="utf-8") as f:
            f.write("=" * 100 + "\n")
            f.write("采购记录分类测试报告\n")
            f.write("=" * 100 + "\n\n")
            
            f.write(f"测试时间: 2025-12-XX\n")
            f.write(f"样本数量: {len(records)}\n")
            f.write(f"有效样本: {valid_samples}\n")
            f.write(f"阈值: {THRESHOLD}\n")
            f.write(f"高置信度样本: {high_confidence_count}\n")
            f.write(f"覆盖率: {coverage_rate:.2%}\n")
            f.write(f"平均置信度: {avg_confidence:.4f}\n\n")
            
            f.write("=" * 100 + "\n")
            f.write("详细日志:\n")
            f.write("=" * 100 + "\n\n")
            
            for log_entry in detailed_logs:
                f.write(log_entry + "\n\n")
            
            f.write("=" * 100 + "\n")
            f.write(f"测试结论: {'✅ 通过 - 达到目标覆盖率' if coverage_rate >= TARGET_COVERAGE else '❌ 未通过 - 未达到目标覆盖率'}\n")
            f.write("=" * 100 + "\n")
        
        print(f"\n📁 详细日志已保存到: {log_file.absolute()}")
        
        # 建议
        if coverage_rate < TARGET_COVERAGE:
            print("\n🔧 改进建议:")
            print("  1. 考虑调整阈值到 {:.3f}".format(np.percentile(confidence_values, 5)))
            print("  2. 增强语义锚点的多样性")
            print("  3. 优化输入文本的预处理")
    else:
        print("❌ 没有有效的测试样本！")
        print("请检查数据库中的记录是否有有效的文本内容")

if __name__ == "__main__":
    main()
