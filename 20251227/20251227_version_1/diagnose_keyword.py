# D:\code\project\scripts\20251227\20251227_version_1\diagnose_keyword.py
from first_stage_keyword import KeywordClassifier

def diagnose():
    clf = KeywordClassifier()
    
    test_texts = [
        ("特克斯县人民医院12月病号服等物资竞价", 0.882),
        ("江西广播电视台关于麦克风/话筒5件的竞价采购", 0.855),
        ("新干县人民医院橱柜采购项目", 0.882),
        ("幼儿图书", 0.54),
        ("台式计算机（2025个人）", None)
    ]
    
    print("🔍 关键词分类诊断报告")
    print("="*60)
    
    for text, expected_conf in test_texts:
        result = clf.classify(text)
        print(f"\n文本: {text}")
        print(f"分类: {result['category']}")
        print(f"置信度: {result['confidence']}")
        if expected_conf:
            diff = result['confidence'] - expected_conf
            print(f"与预期差异: {diff:+.4f}")
        print(f"得分详情: {result.get('scores', {})}")
        if 'details' in result:
            print(f"匹配关键词: {result['details'].get('matched_keywords', [])}")

if __name__ == "__main__":
    diagnose()
