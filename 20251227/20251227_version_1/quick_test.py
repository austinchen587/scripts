# D:\code\project\scripts\20251227\20251227_version_1\quick_test.py
from first_stage_keyword import KeywordClassifier
from second_stage_cosine import CosineVerifier

def test_quick():
    """快速测试"""
    keyword_clf = KeywordClassifier()
    cosine_verifier = CosineVerifier()
    
    test_texts = [
        "特克斯县人民医院12月病号服等物资竞价",
        "江西广播电视台关于麦克风/话筒5件的竞价采购",
        "新干县人民医院橱柜采购项目",
        "幼儿图书",
        "南昌市职业技能培训系统支撑服务项目"
    ]
    
    print("🔍 快速测试")
    print("="*60)
    
    for text in test_texts:
        print(f"\n📝 文本: {text}")
        
        # 第一阶段
        kw_result = keyword_clf.classify(text)
        print(f"  关键词分类: {kw_result['category']} (置信度: {kw_result['confidence']})")
        if 'details' in kw_result:
            print(f"  匹配关键词: {kw_result['details'].get('matched_keywords', [])}")
        
        # 第二阶段（如果余弦验证可用）
        cos_result = cosine_verifier.verify(text, kw_result)
        if cos_result.get('verified', False):
            print(f"  余弦验证: {cos_result['cosine_category']} (置信度: {cos_result['cosine_confidence']})")
            print(f"  是否一致: {cos_result.get('consistent', False)}")
    
    print("\n📊 关键词测试:")
    # 测试关键词匹配
    clf = KeywordClassifier()
    test_cases = [
        ("物资采购项目", ["物资", "采购", "项目"]),
        ("工程咨询服务", ["工程", "咨询", "服务"]),
        ("设备维护服务", ["设备", "维护", "服务"]),
    ]
    
    for text, expected in test_cases:
        result = clf.classify(text)
        print(f"  '{text}' -> {result['category']} (置信度: {result['confidence']})")
        print(f"    匹配: {result['details'].get('matched_keywords', [])}")

if __name__ == "__main__":
    test_quick()
