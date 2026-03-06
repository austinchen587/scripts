# D:\code\project\scripts\20251227\20251227_version_1\run_enhanced_classification.py
"""
运行增强分类系统的主脚本
"""

import sys
from pathlib import Path

# 添加路径
current_dir = Path(__file__).parent
sys.path.append(str(current_dir))

from main_classifier import EnhancedProcurementClassifier

def main():
    """主函数"""
    print("=" * 60)
    print("🔬 增强版采购记录分类系统")
    print("📋 特点：三次分类验证 + 余弦相似度比对")
    print("⏩ 新增：需要复核的样本自动进行余弦相似度匹配")
    print("=" * 60)
    
    # 1. 创建分类器
    print("\n1️⃣ 初始化分类器...")
    classifier = EnhancedProcurementClassifier()
    
    # 2. 从数据库获取随机样本
    print("\n2️⃣ 从数据库获取随机样本...")
    samples = classifier.db.fetch_random_samples(sample_size=100)
    
    if not samples:
        print("❌ 未能获取样本数据，请检查数据库配置")
        return
    
    print(f"✅ 成功获取 {len(samples)} 个样本")
    
    # 3. 批量分类（包含后处理）
    print("\n3️⃣ 开始分类处理（三次验证 + 后处理）...")
    print("-" * 60)
    
    all_results = classifier.classify_batch(samples)
    
    # 4. 输出结果
    print("\n4️⃣ 分类完成，分析结果...")
    print("-" * 60)
    
    stats = classifier.get_statistics()
    
    print(f"📊 总体统计:")
    print(f"   总记录数: {stats['total_records']}")
    print(f"   第一阶段完成: {stats['stage1_completed']} ({stats.get('stage1_percentage', '0%')})")
    print(f"   第二阶段完成: {stats['stage2_completed']} ({stats.get('stage2_percentage', '0%')})")
    print(f"   第三阶段完成: {stats['stage3_completed']} ({stats.get('stage3_percentage', '0%')})")
    print(f"   后处理提升: {stats.get('post_processed', 0)} ({stats.get('stage4_percentage', '0%')})")
    print(f"   高置信度: {stats['high_confidence']} ({stats.get('high_confidence_pct', '0%')})")
    print(f"   中置信度: {stats['medium_confidence']} ({stats.get('medium_confidence_pct', '0%')})")
    print(f"   仍需复核: {stats['low_confidence']} ({stats.get('low_confidence_pct', '0%')})")
    
    # 计算自动分类成功率
    auto_classified = stats["high_confidence"] + stats["medium_confidence"]
    total = stats["total_records"]
    success_rate = (auto_classified / total * 100) if total > 0 else 0
    
    print(f"\n🎯 自动分类成功率: {success_rate:.1f}%")
    print(f"   ⬆️ 通过后处理提升: {stats.get('post_processed', 0)} 条记录")
    
    # 5. 保存报告
    print("\n5️⃣ 生成详细报告...")
    report_file = classifier.save_report(current_dir)
    
    # 6. 示例显示
    print("\n6️⃣ 分类示例:")
    print("-" * 60)
    
    # 显示前5个样本的分类结果
    for i, result in enumerate(all_results[:5]):
        if not result:
            continue
        status = "✅" if not result.get('requires_verification', True) else "⚠️ "
        stage_marker = ""
        if result.get('stage_used') == 4:
            stage_marker = "⏩"
        print(f"{status}{stage_marker} 示例 {i+1}:")
        print(f"   项目名称: {result['project_name'][:40]}...")
        print(f"   分类结果: {result['category']} (置信度: {result['confidence']:.3f})")
        print(f"   使用阶段: 阶段{result['stage_used']}" + ("（后处理）" if result['stage_used'] == 4 else ""))
        print(f"   需要复核: {'是' if result['requires_verification'] else '否'}")
        print()
    
    # 7. 显示最终仍需要复核的样本
    need_review = [r for r in all_results if r and r.get('requires_verification', False)]
    if need_review:
        print(f"⚠️  最终仍需人工复核的样本: {len(need_review)} 个")
        print("-" * 40)
        for i, r in enumerate(need_review):
            print(f"   {i+1}. ID:{r['record_id']}: {r['project_name'][:50]}...")
    else:
        print("✅ 所有样本都达到可接受置信度，无需复核")
    
    # 8. 显示后处理提升的样本
    post_processed = [r for r in all_results if r and r.get('stage_used', 0) == 4]
    if post_processed:
        print(f"\n⏩  通过余弦相似度匹配自动提升的样本: {len(post_processed)} 个")
        print("-" * 40)
        for i, r in enumerate(post_processed[:5]):  # 只显示前5个
            print(f"   {i+1}. ID:{r['record_id']}: {r['project_name'][:50]}...")
        if len(post_processed) > 5:
            print(f"   ... 还有 {len(post_processed)-5} 个")
    
    # 9. 保存详细日志
    print("\n7️⃣ 保存详细分类结果...")
    log_file, json_file = classifier.logger.save_logs()
    print(f"✅ 详细文本日志: {log_file}")
    print(f"✅ 详细JSON结果: {json_file}")
    
    # 10. 显示前10条详细的分类信息
    print("\n" + "="*80)
    print("📋 前10条详细分类信息:")
    print("="*80)
    for i, result in enumerate(all_results[:10]):
        if not result:
            continue
        print(f"\n🔵 记录 #{i+1} (ID: {result.get('record_id', 'N/A')}):")
        print(f"   项目名称: {result.get('project_name', '')}")
        print(f"   分类结果: {result.get('category', 'unknown')}")
        print(f"   置信度: {result.get('confidence', 0):.4f}")
        print(f"   使用阶段: 阶段{result.get('stage_used', 0)}")
        print(f"   需要复核: {'是' if result.get('requires_verification', True) else '否'}")
        decision_chain = result.get("decision_chain", [])
        if decision_chain:
            print(f"   决策链:")
            for j, decision in enumerate(decision_chain):
                print(f"     步骤{j+1}: {decision}")
    
    print(f"\n💾 完整100条记录保存在: {json_file}")
    
    print("\n" + "=" * 60)
    print("🎯 分类任务完成!")
    print(f"📊 自动分类成功率: {success_rate:.1f}% ({auto_classified}/{total})")
    print(f"📁 详细结果已保存到: {current_dir}/")
    print(f"📄 分类报告: {report_file}")
    print("=" * 60)
    
    return all_results, log_file, json_file

if __name__ == "__main__":
    main()
