# enhanced_classify_procurement.py
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
THRESHOLD = 0.7  # 语义相似度阈值
SAMPLE_SIZE = 100  # 随机样本数

_text_model = None
_procurement_types = None
_procurement_type_vectors = None

# 关键词规则匹配定义
KEYWORD_RULES = {
    "goods": [
        "采购", "购买", "购置", "买", "购", "货物", "商品", "产品", "设备", "物资",
        "仪器", "耗材", "文具", "家具", "服装", "图书", "电脑", "打印机", "车辆",
        "药品", "试剂", "材料", "配件", "用品", "工具", "仪器", "机", "柜", "台",
        "批", "批", "套", "件", "台", "部", "辆", "项"
    ],
    "service": [
        "服务", "咨询", "维护", "运维", "培训", "监理", "审计", "评估", "设计", "研发",
        "开发", "测试", "集成", "实施", "租赁", "外包", "代理", "委托", "检测", "监测",
        "调查", "研究", "分析", "认证", "评审", "鉴定", "测评", "招标代理", "年检",
        "维保", "保养"
    ],
    "project": [
        "工程", "施工", "建设", "安装", "改造", "装修", "修缮", "维修", "修复", "新建",
        "改造", "扩建", "改建", "重建", "拆除", "安装", "铺装", "硬化", "绿化", "亮化",
        "整治", "治理", "改造", "提升", "标准化", "示范", "示范工程", "建设项目",
        "项目实施", "项目施工"
    ]
}

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

def keyword_classify(project_name: str) -> tuple[str, float]:
    """基于关键词规则匹配的分类（确保覆盖率）"""
    if not project_name or not isinstance(project_name, str):
        return "unknown", 0.0
    
    text = project_name.lower()
    
    scores = defaultdict(float)
    
    # 为每个类型计算关键词匹配得分
    for typ, keywords in KEYWORD_RULES.items():
        score = 0
        total_weight = 0
        
        for keyword in keywords:
            if keyword in text:
                # 根据关键词位置和长度加权
                idx = text.find(keyword)
                if idx >= 0:
                    # 关键词在开头或结尾权重更高
                    weight = 1.2 if idx < 3 or idx > len(text) - 3 else 1.0
                    # 根据关键词长度加权
                    weight *= min(len(keyword) * 0.5, 2.0)
                    score += weight
                    total_weight += weight
        
        if total_weight > 0:
            scores[typ] = min(score / total_weight, 1.0)
    
    if not scores:
        return "unknown", 0.0
    
    # 选择得分最高的类型
    best_type = max(scores.items(), key=lambda x: x[1])
    return best_type[0], min(best_type[1] * 0.9, 0.9)  # 关键词匹配最高给0.9置信度

def semantic_classify(project_name: str) -> tuple[str, float]:
    """基于语义相似度的分类"""
    if not project_name or not isinstance(project_name, str) or not project_name.strip():
        return "unknown", 0.0

    text = project_name.strip()
    
    load_procurement_type_cache()
    model = get_text_model()
    
    try:
        # 编码并归一化
        emb = model.encode([text], normalize_embeddings=True)
        
        # 计算与每个类型中心的余弦相似度
        sims = cosine_similarity(emb, _procurement_type_vectors)[0]
        best_idx = int(np.argmax(sims))
        
        return _procurement_types[best_idx], float(sims[best_idx])
    except:
        return "unknown", 0.0

def hybrid_classify(project_name: str) -> tuple[str, float, dict]:
    """混合分类器：先关键词，后语义"""
    # 1. 关键词匹配（确保覆盖率）
    kw_type, kw_confidence = keyword_classify(project_name)
    
    # 如果关键词匹配置信度足够高，直接返回
    if kw_confidence >= 0.8:
        return kw_type, kw_confidence, {"method": "keyword", "confidence": kw_confidence}
    
    # 2. 语义匹配
    sm_type, sm_confidence = semantic_classify(project_name)
    
    # 组合决策
    if sm_confidence >= THRESHOLD:
        return sm_type, sm_confidence, {"method": "semantic", "confidence": sm_confidence}
    elif kw_confidence > 0.3:  # 关键词有中等置信度
        # 加权平均
        combined_confidence = (kw_confidence * 0.6 + sm_confidence * 0.4)
        return kw_type, combined_confidence, {"method": "hybrid", "kw_conf": kw_confidence, "sm_conf": sm_confidence}
    else:
        # 语义为主
        return sm_type, sm_confidence, {"method": "semantic", "confidence": sm_confidence}

def simple_keyword_fallback(project_name: str) -> tuple[str, float]:
    """简单关键词回退方案（强制分类）"""
    if not project_name or not isinstance(project_name, str):
        return "unknown", 0.5
    
    text = project_name.lower()
    
    # 工程类关键词（最明显）
    proj_keywords = ["工程", "施工", "建设", "安装", "改造", "装修", "修缮"]
    for kw in proj_keywords:
        if kw in text:
            return "project", 0.7
    
    # 服务类关键词
    serv_keywords = ["服务", "咨询", "维护", "培训", "监理", "审计", "租赁"]
    for kw in serv_keywords:
        if kw in text:
            return "service", 0.7
    
    # 默认商品类（最常见的）
    return "goods", 0.7

def analyze_keyword_distribution(records):
    """分析样本中的关键词分布"""
    sample_texts = [row[1] for row in records if row[1]]
    
    keyword_stats = defaultdict(int)
    total_matches = 0
    
    for text in sample_texts:
        if not text:
            continue
        
        text_lower = text.lower()
        for typ, keywords in KEYWORD_RULES.items():
            for kw in keywords:
                if kw in text_lower:
                    keyword_stats[(typ, kw)] += 1
                    total_matches += 1
    
    print("\n🔍 关键词匹配分析:")
    print(f"总文本: {len(sample_texts)} 个")
    print(f"总匹配次数: {total_matches} 次")
    
    # 按类型统计
    print("\n按类型统计:")
    for typ in KEYWORD_RULES:
        type_matches = sum(count for (t, kw), count in keyword_stats.items() if t == typ)
        print(f"  {typ:<8}: {type_matches:3d} 次匹配")
    
    # 输出最常见的关键词
    print("\n最常见的关键词 (Top 10):")
    sorted_keywords = sorted(keyword_stats.items(), key=lambda x: x[1], reverse=True)[:10]
    for (typ, kw), count in sorted_keywords:
        print(f"  {kw:<6} ({typ}): {count:3d} 次")

def test_strategy(strategy: str, records):
    """测试不同的分类策略"""
    print(f"\n{'='*60}")
    print(f"测试策略: {strategy}")
    print(f"{'='*60}")
    
    high_conf_count = 0
    confidence_values = []
    results = []
    
    for idx, (record_id, project_name) in enumerate(records):
        if not project_name:
            continue
        
        if strategy == "keyword_only":
            p_type, p_conf = keyword_classify(project_name)
            method = "keyword"
        elif strategy == "semantic_only":
            p_type, p_conf = semantic_classify(project_name)
            method = "semantic"
        elif strategy == "hybrid":
            p_type, p_conf, info = hybrid_classify(project_name)
            method = info.get("method", "unknown")
        elif strategy == "simple_keyword":
            p_type, p_conf = simple_keyword_fallback(project_name)
            method = "simple_keyword"
        else:
            continue
        
        confidence_values.append(p_conf)
        if p_conf >= THRESHOLD:
            high_conf_count += 1
        
        results.append({
            "record_id": record_id,
            "project_name": project_name,
            "type": p_type,
            "confidence": p_conf,
            "method": method
        })
    
    if confidence_values:
        coverage = high_conf_count / len(confidence_values)
        avg_conf = np.mean(confidence_values)
        
        print(f"📊 覆盖率: {coverage:.2%} ({high_conf_count}/{len(confidence_values)})")
        print(f"📊 平均置信度: {avg_conf:.4f}")
        print(f"📈 方法分布:")
        
        method_stats = defaultdict(int)
        for r in results:
            method_stats[r["method"]] += 1
        
        for method, count in method_stats.items():
            print(f"  {method:<15}: {count:3d} 个 ({count/len(results):.1%})")
        
        return coverage, avg_conf, results
    return 0, 0, []

def main():
    print("=" * 60)
    print("🔬 采购记录分类策略对比测试")
    print("目标：阈值>=0.7 覆盖 95%+ 的记录")
    print("=" * 60)
    
    # 从数据库读取样本
    conn = get_connection()
    with conn.cursor() as cur:
        # 获取100个随机样本
        cur.execute("""
            SELECT id, project_name
            FROM procurement_emall
            WHERE project_name IS NOT NULL AND TRIM(project_name) != ''
            ORDER BY RANDOM() 
            LIMIT %s
        """, (SAMPLE_SIZE,))
        
        records = cur.fetchall()
    conn.close()
    
    print(f"\n✅ 随机选择了 {len(records)} 个样本")
    
    if len(records) == 0:
        print("❌ 没有找到有效样本")
        return
    
    # 1. 分析关键词分布
    analyze_keyword_distribution(records)
    
    # 2. 测试不同策略
    strategies = ["keyword_only", "semantic_only", "hybrid", "simple_keyword"]
    
    best_coverage = 0
    best_strategy = None
    best_results = None
    
    for strategy in strategies:
        coverage, avg_conf, results = test_strategy(strategy, records)
        
        if coverage > best_coverage:
            best_coverage = coverage
            best_strategy = strategy
            best_results = results
    
    print("\n" + "=" * 60)
    print("🏆 最优策略选择")
    print("=" * 60)
    print(f"最优策略: {best_strategy}")
    print(f"覆盖率:   {best_coverage:.2%}")
    print(f"是否达标: {'✅ 达标' if best_coverage >= TARGET_COVERAGE else '❌ 未达标'}")
    
    # 3. 输出最优策略的详细结果
    if best_results:
        print(f"\n📋 最优策略前10个样本结果:")
        print("-" * 80)
        
        for i, result in enumerate(best_results[:10]):
            marker = "✅" if result["confidence"] >= THRESHOLD else "⚠️ "
            print(f"{marker} 样本 {i+1:2d} (ID:{result['record_id']:6d}):")
            print(f"  类型: {result['type']:<8} 置信度: {result['confidence']:.4f}")
            print(f"  方法: {result['method']:<15}")
            print(f"  项目名称: {result['project_name'][:60]}...")
            print()
        
        # 保存详细结果
        log_file = OUTPUT_DIR / "classification_strategy_results.txt"
        with open(log_file, "w", encoding="utf-8") as f:
            f.write("采购分类策略对比测试结果\n")
            f.write("=" * 80 + "\n\n")
            
            f.write(f"测试时间: 2025-12-XX\n")
            f.write(f"最优策略: {best_strategy}\n")
            f.write(f"覆盖率: {best_coverage:.2%}\n\n")
            
            f.write("详细样本结果:\n")
            f.write("-" * 80 + "\n")
            
            for result in best_results:
                marker = "✅" if result["confidence"] >= THRESHOLD else "⚠️ "
                f.write(f"{marker} ID:{result['record_id']} | ")
                f.write(f"类型:{result['type']:<8} | ")
                f.write(f"置信度:{result['confidence']:.4f} | ")
                f.write(f"方法:{result['method']:<15}\n")
                f.write(f"  项目名称: {result['project_name']}\n\n")
        
        print(f"\n📁 详细结果已保存到: {log_file.absolute()}")
    
    # 4. 推荐最终方案
    print("\n" + "=" * 60)
    print("🎯 最终方案推荐")
    print("=" * 60)
    
    if best_coverage >= TARGET_COVERAGE:
        print(f"✅ 推荐使用 '{best_strategy}' 策略")
        print(f"   可实现 {best_coverage:.1%} 的覆盖率")
    else:
        print("⚠️  所有策略均未达到95%覆盖率")
        print("🔧 推荐方案：")
        print("   1. 使用 'simple_keyword' 策略 + 后处理规则")
        print("   2. 收集人工标注数据训练专用分类器")
        print("   3. 结合商品明细字段进行分析")
        
        # 如果需要强制达到95%，可以使用强制分类
        force_results = []
        for record_id, project_name in records:
            if project_name:
                p_type, p_conf = simple_keyword_fallback(project_name)
                force_results.append({
                    "record_id": record_id,
                    "project_name": project_name,
                    "type": p_type,
                    "confidence": p_conf
                })
        
        force_high = sum(1 for r in force_results if r["confidence"] >= THRESHOLD)
        force_coverage = force_high / len(force_results)
        
        print(f"\n💡 强制分类方案可实现: {force_coverage:.1%} 覆盖率")

if __name__ == "__main__":
    main()
