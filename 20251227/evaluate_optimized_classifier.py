# evaluate_optimized_classifier.py
import re
import random

def optimized_classify_with_details(project_name: str) -> tuple[str, float, list]:
    """优化分类器（带详细决策日志）"""
    if not project_name:
        return "goods", 0.7, ["默认分类: 商品类"]
    
    text = project_name.lower()
    decision_log = []
    
    # 1. 工程类检测
    proj_patterns = [
        (r".*工程$", 0.95),        # "xxx工程"
        (r".*建设项目$", 0.95),     # "xxx建设项目"  
        (r".*施工项目$", 0.95),     # "xxx施工项目"
        (r".*改造项目$", 0.95),     # "xxx改造项目"
        (r".*维修项目$", 0.95),     # "xxx维修项目"
        (r".*安装工程$", 0.95),     # "xxx安装工程"
        (r".*整治工程$", 0.95),     # "xxx整治工程"
        (r".*建设工程$", 0.95),     # "xxx建设工程"
        (r".*建设项目$", 0.95),     # "xxx建设项目"
        (r".*工程项目$", 0.95),     # "xxx工程项目"
    ]
    
    for pattern, conf in proj_patterns:
        if re.match(pattern, text):
            decision_log.append(f"模式匹配: '{pattern}' -> 工程类 (置信度: {conf})")
            return "project", conf, decision_log
    
    # 2. 服务类检测
    serv_patterns = [
        (r".*服务项目$", 0.95),     # "xxx服务项目"
        (r".*咨询服务$", 0.95),     # "xxx咨询服务"
        (r".*运维服务$", 0.95),     # "xxx运维服务"
        (r".*培训服务$", 0.95),     # "xxx培训服务"
        (r".*设计服务$", 0.95),     # "xxx设计服务"
        (r".*评估服务$", 0.95),     # "xxx评估服务"
        (r".*监理服务$", 0.95),     # "xxx监理服务"
        (r".*审计服务$", 0.95),     # "xxx审计服务"
        (r".*研究$", 0.90),         # "xxx研究"
        (r"创作.*", 0.90),          # "创作xxx"
        (r".*咨询服务$", 0.90),     # "xxx咨询服务"
    ]
    
    for pattern, conf in serv_patterns:
        if re.match(pattern, text):
            decision_log.append(f"模式匹配: '{pattern}' -> 服务类 (置信度: {conf})")
            return "service", conf, decision_log
    
    # 3. 商品类检测
    goods_patterns = [
        (r".*采购项目$", 0.95),     # "xxx采购项目"
        (r".*购买项目$", 0.95),     # "xxx购买项目"
        (r".*采购公告$", 0.95),     # "xxx采购公告"
        (r".*采购方案$", 0.95),     # "xxx采购方案"
        (r".*询价公告$", 0.95),     # "xxx询价公告"
        (r".*竞价采购$", 0.95),     # "xxx竞价采购"
        (r".*招标采购$", 0.95),     # "xxx招标采购"
        (r".*设备采购$", 0.95),     # "xxx设备采购"
        (r".*物资采购$", 0.95),     # "xxx物资采购"
    ]
    
    for pattern, conf in goods_patterns:
        if re.match(pattern, text):
            decision_log.append(f"模式匹配: '{pattern}' -> 商品类 (置信度: {conf})")
            return "goods", conf, decision_log
    
    # 4. 关键词强度分析
    keyword_scores = {
        "project": 0,
        "service": 0, 
        "goods": 0
    }
    
    # 工程类关键词（高权重）
    for kw in ["工程", "施工", "建设", "安装", "改造", "装修", "修缮", "修复", "新建"]:
        if kw in text:
            keyword_scores["project"] += 3 if kw in ["工程", "施工", "建设"] else 2
    
    # 服务类关键词（中等权重）
    for kw in ["服务", "咨询", "维护", "运维", "培训", "监理", "审计", "评估", "设计", "研发"]:
        if kw in text:
            keyword_scores["service"] += 3 if kw == "服务" else 2
    
    # 商品类关键词（中等权重）
    for kw in ["采购", "购买", "购置", "设备", "用品", "物资", "耗材"]:
        if kw in text:
            keyword_scores["goods"] += 3 if kw in ["采购", "购买"] else 2
    
    # 5. 决策逻辑
    if keyword_scores["project"] > 0 or keyword_scores["service"] > 0 or keyword_scores["goods"] > 0:
        # 找出最高分类型
        best_type = max(keyword_scores.items(), key=lambda x: x[1])
        if best_type[1] > 0:
            # 计算置信度：根据领先幅度
            scores = list(keyword_scores.values())
            sorted_scores = sorted(scores, reverse=True)
            if sorted_scores[0] - sorted_scores[1] >= 2:  # 有明显领先
                confidence = 0.85
            elif sorted_scores[0] > 0:
                confidence = 0.75
            else:
                confidence = 0.7
            
            decision_log.append(f"关键词分析: {keyword_scores}")
            decision_log.append(f"决策: {best_type[0]} (得分: {best_type[1]}, 置信度: {confidence})")
            return best_type[0], confidence, decision_log
    
    # 6. 默认分类
    decision_log.append("未匹配任何模式，使用默认分类: 商品类")
    return "goods", 0.7, decision_log

def manual_evaluate():
    """人工评估准确率"""
    # 从您的数据中选取代表性的30个样本
    test_samples = [
        # ✅ 应容易分类的（预计准确率 >95%）
        ("风雷楼、云鹰楼楼顶维修项目", "project"),
        ("赣州市公共文化服务中心导引服务升级采购项目", "service"), 
        ("2025年高考机房标准化设备采购", "goods"),
        ("临川区鹏田乡鹏田村村内道路维修工程", "project"),
        ("南昌市象湖风景区管理处2026年-2027年食堂劳务外包服务项目", "service"),
        ("NVR硬盘采购", "goods"),
        ("修水县第一人民医院急诊办公用房改造项目", "project"),
        ("档案数字化服务", "service"),
        ("办公设备打印机采购", "goods"),
        
        # ⚠️ 可能困难的（预计准确率 ~85%）
        ("2025-2026学年全市中学教学质量检测和高考模拟考试阅卷服务项目", "service"),
        ("创作一首客家文艺精品歌曲", "service"),
        ("景德镇市能源发展现状及对策课题研究", "service"),
        ("语音转写服务采购项目", "goods"),  # "服务采购"还是"服务项目采购"？
        ("智能制造学院2025下半年实训室设备维修、维保服务", "service"),  # 混合了"维修"和"服务"
        ("关于采购使用无人机提升城管服务水平的事宜", "goods"),  # 采购什么？服务？设备？
        
        # ❌ 非常困难的（预计准确率 <80%）
        ("基于大数据专科能力提升项目", "service"),  # "项目"误导为工程
        ("麻丘镇高胡村新建冲水式厕所项目", "project"),  # 新建项目是工程
        ("乐平塔山工业园区大气环境走航监测项目", "service"),  # "监测项目"是服务
        ("人工智能知识数字资源库", "goods"),  # 资源库是商品还是服务？
    ]
    
    print("🧪 优化分类器准确率评估")
    print("=" * 80)
    
    correct_count = 0
    results = []
    
    for idx, (project_name, expected_type) in enumerate(test_samples, 1):
        predicted_type, confidence, log = optimized_classify_with_details(project_name)
        is_correct = predicted_type == expected_type
        
        if is_correct:
            correct_count += 1
            symbol = "✅"
        else:
            symbol = "❌"
        
        results.append({
            "index": idx,
            "name": project_name,
            "expected": expected_type,
            "predicted": predicted_type,
            "correct": is_correct,
            "confidence": confidence,
            "log": log
        })
        
        # 显示结果
        print(f"{symbol} 样本 {idx:2d}: {project_name[:50]:<50}...")
        print(f"    期望: {expected_type:<8} | 预测: {predicted_type:<8} | 置信度: {confidence:.2f}")
        
        if not is_correct:
            print(f"    🔍 决策过程: {log[-1] if log else '无日志'}")
        print()
    
    # 统计结果
    accuracy = correct_count / len(test_samples)
    print("=" * 80)
    print(f"📊 测试结果:")
    print(f"   测试样本数: {len(test_samples)}")
    print(f"   正确分类数: {correct_count}")
    print(f"   准确率: {accuracy:.1%}")
    
    # 按类型统计
    print(f"\n📈 按类别统计:")
    type_stats = {}
    for r in results:
        typ = r["expected"]
        if typ not in type_stats:
            type_stats[typ] = {"total": 0, "correct": 0}
        type_stats[typ]["total"] += 1
        if r["correct"]:
            type_stats[typ]["correct"] += 1
    
    for typ, stats in type_stats.items():
        acc = stats["correct"] / stats["total"] if stats["total"] > 0 else 0
        print(f"   {typ:<8}: {stats['correct']}/{stats['total']} = {acc:.1%}")
    
    return results, accuracy

if __name__ == "__main__":
    results, accuracy = manual_evaluate()
    
    # 给出最终评估
    print("\n" + "=" * 80)
    print("🎯 最终评估结论:")
    print("=" * 80)
    
    if accuracy >= 0.90:
        print("✅ 优化方案效果良好，准确率约 90-95%")
        print("💡 建议直接在生产环境使用")
    elif accuracy >= 0.85:
        print("⚠️  优化方案效果中等，准确率约 85-90%")
        print("💡 建议先在小范围测试，收集反馈后优化")
    else:
        print("❌ 优化方案效果不理想，准确率 <85%")
        print("💡 建议：")
        print("   1. 收集更多标注数据")
        print("   2. 考虑混合模型方案")
        print("   3. 优化关键词规则")
