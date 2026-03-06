# D:\code\project\scripts\20251227\20251227_version_1\first_stage_keyword.py
"""
第一阶段：关键词分类器
基于关键词规则的快速分类
"""

import re
from collections import defaultdict

class KeywordClassifier:
    def __init__(self):
        self.keyword_patterns = {
            "project": {
                "strong": [
                    r"工程$", r"施工$", r"建设$", r"安装$", r"改造$", 
                    r"维修$", r"修缮$", r"整治$", r"治理$"
                    # ⬇️ 移除了 "项目$" —— 这是关键改动
                ],
                "medium": ["工程", "施工", "建设", "安装", "改造"],
                "weak": ["施工", "建设"]  # ⬇️ 移除了 "项目"
            },
            "service": {
                "strong": [
                    r"服务$", r"咨询$", r"培训$", r"维护$", r"运维$",
                    r"监理$", r"审计$", r"评估$", r"设计$", r"外包$"
                ],
                "medium": ["服务", "咨询", "培训", "维护", "监理"],
                "weak": ["服务", "咨询", "外包"]
            },
            "goods": {
                "strong": [
                    r"采购$", r"购买$", r"购置$", r"货物$", r"物资$",
                    r"设备$", r"耗材$", r"用品$", r"商品$", r"产品$"
                ],
                "medium": ["采购", "购买", "设备", "用品", "物资", "竞价"],  # ⬅️ 新增 "竞价"
                "weak": ["采购", "设备", "用品"]
            }
        }
        
        self.weights = {
            "strong": 3.0,
            "medium": 2.0,
            "weak": 1.0
        }
    
    def classify(self, text):
        if not text or not isinstance(text, str):
            return {"category": "unknown", "confidence": 0.0}
        
        text_lower = text.lower()
        scores = defaultdict(float)
        matched_details = defaultdict(list)
        
        for category, patterns in self.keyword_patterns.items():
            category_score = 0
            weight_total = 0
            matched_keywords = []
            
            # strong: 必须结尾匹配
            for pattern in patterns["strong"]:
                if re.search(pattern, text_lower):
                    category_score += self.weights["strong"]
                    weight_total += self.weights["strong"]
                    keyword_str = pattern.rstrip('$')
                    matched_keywords.append(f"强:{keyword_str}")
                    matched_details[category].append(f"强:{keyword_str}")
            
            # medium
            for keyword in patterns["medium"]:
                if keyword in text_lower:
                    category_score += self.weights["medium"]
                    weight_total += self.weights["medium"]
                    matched_keywords.append(f"中:{keyword}")
                    matched_details[category].append(f"中:{keyword}")
            
            # weak
            for keyword in patterns["weak"]:
                if keyword in text_lower:
                    category_score += self.weights["weak"]
                    weight_total += self.weights["weak"]
                    matched_keywords.append(f"弱:{keyword}")
                    matched_details[category].append(f"弱:{keyword}")
            
            if weight_total > 0:
                normalized_score = category_score / (weight_total * 3.0)  # 归一化到 [0,1]
                # 置信度 = 基础分 + 关键词数量激励（上限 0.85）
                count_bonus = min(len(matched_keywords) * 0.05, 0.15)
                confidence = min(normalized_score * 0.7 + count_bonus + 0.1, 0.85)
                
                # 强关键词额外提升（但不超过 0.9）
                if any(k.startswith("强:") for k in matched_keywords):
                    confidence = min(confidence * 1.1, 0.90)
                
                scores[category] = round(confidence, 4)
        
        if not scores:
            return {
                "category": "goods", 
                "confidence": 0.4,
                "scores": {},
                "details": {"matched_keywords": [], "reason": "无关键词匹配"}
            }
        
        best_category = max(scores.items(), key=lambda x: x[1])
        sorted_vals = sorted(scores.values(), reverse=True)
        
        # 若最高分与其他类别差距小，降低置信度
        if len(sorted_vals) > 1 and (sorted_vals[0] - sorted_vals[1]) < 0.1:
            final_conf = best_category[1] * 0.85
        else:
            final_conf = best_category[1]
        
        return {
            "category": best_category[0],
            "confidence": round(final_conf, 4),
            "scores": dict(scores),
            "details": {
                "matched_keywords": matched_details[best_category[0]],
                "reason": f"匹配关键词: {len(matched_details[best_category[0]])}个"
            }
        }