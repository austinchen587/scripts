# test_procurement_classification_pname.py
import sys
import json
import random
import numpy as np
from pathlib import Path
from tqdm import tqdm
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
        with open(OUTPUT_DIR / "procurement_types_pname.json", "r", encoding="utf-8") as f:
            _procurement_types = json.load(f)
        _procurement_type_vectors = np.load(OUTPUT_DIR / "procurement_type_vectors_pname.npy")

def classify_procurement_type(project_name: str) -> tuple[str, float]:
    """基于 project_name 进行采购分类"""
    if not project_name or not isinstance(project_name, str) or not project_name.strip():
        return "unknown", 0.0

    text = project_name.strip()
    
    load_procurement_type_cache()
    model = get_text_model()
    
    # 编码并归一化
    emb = model.encode([text], normalize_embeddings=True)
    
    # 计算与每个类型中心的余弦相似度
    sims = cosine_similarity(emb, _procurement_type_vectors)[0]
    best_idx = int(np.argmax(sims))
    
    return _procurement_types[best_idx], float(sims[best_idx])

def get_top3_predictions(project_name: str) -> list:
    """获取top3预测结果"""
    if not project_name or not isinstance(project_name, str) or not project_name.strip():
        return []
    
    load_procurement_type_cache()
    model = get_text_model()
    
    text = project_name.strip()
    emb = model.encode([text], normalize_embeddings=True)
    sims = cosine_similarity(emb, _procurement_type_vectors)[0]
    
    # 获取top3
    top3_indices = np.argsort(sims)[-3:][::-1]
    top3_results = []
    
    for idx in top3_indices:
        top3_results.append({
            "type": _procurement_types[idx],
            "confidence": float(sims[idx])
        })
    
    return top3_results

def main():
    print("=" * 60)
    print("📊 采购记录分类测试（仅使用 project_name）")
    print(f"测试配置：{SAMPLE_SIZE}个随机样本，置信度阈值={THRESHOLD}")
    print("目标：阈值>=0.7 覆盖 {:.0f}%+ 的记录".format(TARGET_COVERAGE * 100))
    print("=" * 60)
    
    # 加载模型和缓存
    get_text_model()
    load_procurement_type_cache()
    
    # 从数据库读取仅包含project_name的记录
    conn = get_connection()
    with conn.cursor() as cur:
        # 获取有project_name的记录
        cur.execute("""
            SELECT id, project_name
            FROM procurement_emall
            WHERE project_name IS NOT NULL AND TRIM(project_name) != ''
            ORDER BY RANDOM() 
            LIMIT %s
        """, (SAMPLE_SIZE,))
        
        records = cur.fetchall()
    conn.close()
    
    print(f"\n✅ 随机选择了 {len(records)} 个包含project_name的样本")
    
    if len(records) < SAMPLE_SIZE:
        print(f"⚠️  警告：数据库中有project_name的记录不足{SAMPLE_SIZE}条")
        print(f"    实际找到 {len(records)} 条记录，继续测试...")
    
    # 测试结果统计
    high_confidence_count = 0
    low_confidence_count = 0
    confidence_values = []
    
    # 详细日志存储
    detailed_logs = []
    classified_results = []
    
    print("\n" + "-" * 100)
    print("📝 详细分类日志:")
    print("-" * 100)
    
    # 逐条分类测试
    for idx, (record_id, project_name) in enumerate(tqdm(records, desc="测试进度", ncols=80)):
        if not project_name or not isinstance(project_name, str):
            continue
            
        p_name = project_name.strip()
        
        # 进行分类
        p_type, p_conf = classify_procurement_type(p_name)
        
        # 获取top3预测（用于分析）
        top3 = get_top3_predictions(p_name)
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
        log_entry = f"{confidence_marker} 样本 {idx+1:3d} (ID:{record_id:6d}):"
        log_entry += f" 类型={p_type:<8}"
        log_entry += f" 置信度={p_conf:.4f}"
        log_entry += f" {'🔺达标' if meets_threshold else '🔻未达标'}"
        log_entry += f"\n   项目名称: {p_name}"
        
        # 添加top3分析（如果未达标）
        if not meets_threshold and top3:
            log_entry += f"\n   Top3预测: "
            for pred in top3[:3]:
                log_entry += f"{pred['type']}({pred['confidence']:.3f}) "
        
        detailed_logs.append(log_entry)
        classified_results.append({
            "record_id": record_id,
            "project_name": p_name,
            "type": p_type,
            "confidence": p_conf,
            "top3": top3
        })
        
        # 只显示部分详细日志，避免过多输出
        if idx < 20 or not meets_threshold or idx % 10 == 0:
            print(log_entry)
    
    print("\n" + "=" * 100)
    print("📊 测试结果汇总:")
    print("=" * 100)
    
    if confidence_values:
        valid_samples = len(confidence_values)
        # 计算覆盖率
        coverage_rate = high_confidence_count / valid_samples if valid_samples > 0 else 0
        avg_confidence = np.mean(confidence_values)
        
        print(f"📈 总样本数: {len(records)}")
        print(f"📄 有效样本数: {valid_samples}")
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
            pct = count / len(confidence_values)
            bar = "█" * int(pct * 50)
            print(f"  {low:.2f}-{high:.2f}: {count:3d} 个 ({pct:.1%}) {bar}")
        
        # 类型分布
        print(f"\n📊 类型分布:")
        type_counts = {}
        for result in classified_results:
            typ = result["type"]
            type_counts[typ] = type_counts.get(typ, 0) + 1
        
        for typ, count in type_counts.items():
            pct = count / valid_samples
            print(f"  {typ:<8}: {count:3d} 个 ({pct:.1%})")
        
        # 保存详细结果到文件
        log_file = OUTPUT_DIR / "procurement_test_log_pname.txt"
        with open(log_file, "w", encoding="utf-8") as f:
            f.write("=" * 100 + "\n")
            f.write("采购记录分类测试报告（仅使用project_name）\n")
            f.write("=" * 100 + "\n\n")
            
            f.write(f"测试时间: 2025-12-XX\n")
            f.write(f"总样本数: {len(records)}\n")
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
            
            # 添加低置信度样本分析
            low_conf_samples = [r for r in classified_results if r["confidence"] < THRESHOLD]
            if low_conf_samples:
                f.write("=" * 100 + "\n")
                f.write("低置信度样本分析:\n")
                f.write("=" * 100 + "\n\n")
                
                for sample in low_conf_samples[:20]:  # 只显示前20个
                    f.write(f"ID: {sample['record_id']}\n")
                    f.write(f"项目名称: {sample['project_name']}\n")
                    f.write(f"预测类型: {sample['type']} ({sample['confidence']:.4f})\n")
                    f.write(f"Top3预测: ")
                    for pred in sample["top3"][:3]:
                        f.write(f"{pred['type']}({pred['confidence']:.3f}) ")
                    f.write("\n\n")
            
            f.write("=" * 100 + "\n")
            if coverage_rate >= TARGET_COVERAGE:
                f.write("✅ 测试通过 - 达到目标覆盖率\n")
            else:
                f.write("❌ 测试未通过 - 未达到目标覆盖率\n")
                f.write(f"当前覆盖率: {coverage_rate:.2%}\n")
                f.write(f"目标覆盖率: {TARGET_COVERAGE:.0%}\n")
            f.write("=" * 100 + "\n")
        
        print(f"\n📁 详细日志已保存到: {log_file.absolute()}")
        
        # 改进建议
        if coverage_rate < TARGET_COVERAGE:
            print("\n🔧 改进建议:")
            print(f"  1. 当前第5百分位置信度: {np.percentile(confidence_values, 5):.3f}")
            print(f"  2. 推荐阈值调整到: {np.percentile(confidence_values, 5):.3f}")
            print(f"  3. 扩大语义锚点词汇库")
            print(f"  4. 分析{len(low_conf_samples)}个低置信度样本的project_name特征")
            
            # 显示一些低置信度样本的project_name
            print(f"\n📋 低置信度样本示例（前5个）:")
            for sample in low_conf_samples[:5]:
                print(f"  项目名称: {sample['project_name'][:50]}... (置信度: {sample['confidence']:.3f})")
    else:
        print("❌ 没有有效的测试样本！")

if __name__ == "__main__":
    main()
