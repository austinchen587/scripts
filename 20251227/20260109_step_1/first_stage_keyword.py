# D:\code\project\scripts\20251227\20260109_step_1\first_stage_keyword.py
"""
第一阶段：关键词分类器 (最终修复版)
1. 修复了评分公式导致的低置信度 Bug
2. 修复了 matched_keywords 未定义变量错误
3. 增强了对服务类（审计/培训/维保）的保护，防止被工程类误判
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
                ],
                "medium": ["工程", "施工", "建设", "安装", "改造"],
                "weak": ["施工", "建设"]
            },
            "service": {
                "strong": [
                    r"服务$", r"咨询$", r"培训$", r"维护$", r"运维$",
                    r"监理$", r"审计$", r"评估$", r"设计$", r"外包$",
                    r"检测$", r"测绘$", r"租赁$", r"保险$",
                    # ⬇️ 新增：针对日志中漏掉的服务词
                    r"接口$", r"对接$", r"修剪$", r"清理$", r"劳务$"
                ],
                "medium": ["服务", "咨询", "培训", "维护", "监理", "检测", "调试", "接入"],
                "weak": ["服务", "咨询", "外包"]
            },
            "goods": {
                "strong": [
                    r"采购$", r"购买$", r"购置$", r"货物$", r"物资$",
                    r"设备$", r"耗材$", r"用品$", r"商品$", r"产品$"
                ],
                "medium": ["采购", "购买", "设备", "用品", "物资"], 
                # ⬇️ 关键修改：把 "竞价" 移到 weak 或者直接删掉
                # 因为 "服务竞价" 也是竞价，"竞价" 这个词没有分类区分度！
                "weak": ["采购", "设备", "用品", "竞价"] 
            }
        }
        
        # 工程排他性特征（遇到这些词，极大可能是工程）
        self.project_exclusive_indicators = [
            "维修改造", "加固工程", "迁改工程", "治理工程", 
            "整治项目", "配套设施", "修缮工程", "提质改造"
        ]

        # 服务排他性特征（遇到这些词，极大可能是服务，优先于工程）
        self.service_dominant_keywords = [
            "审计", "培训", "检测", "运维", "维保", "租赁", "劳务", "核算", "清查",
            "接口", "对接", "修剪", "清理"  # ⬅️ 新增这些
        ]
        
        self.weights = {
            "strong": 3.0,
            "medium": 2.0,
            "weak": 1.0
        }
    
    def classify(self, text):
        if not text or not isinstance(text, str):
            return {"category": "unknown", "confidence": 0.0}
        
        text_lower = text.lower()
        # 预处理：移除末尾通用的"项目"二字，避免干扰
        if text_lower.endswith("项目"):
            search_text = text_lower[:-2]
        else:
            search_text = text_lower
            
        scores = defaultdict(float)
        matched_details = defaultdict(list)
        
        # 1. 常规关键词匹配
        for category, patterns in self.keyword_patterns.items():
            category_score = 0
            weight_total = 0
            
            # strong
            for pattern in patterns["strong"]:
                if re.search(pattern, search_text):
                    category_score += self.weights["strong"]
                    weight_total += self.weights["strong"]
                    matched_details[category].append(f"强:{pattern.rstrip('$')}")
            
            # medium
            for keyword in patterns["medium"]:
                if keyword in search_text:
                    category_score += self.weights["medium"]
                    weight_total += self.weights["medium"]
                    matched_details[category].append(f"中:{keyword}")
            
            # weak
            for keyword in patterns["weak"]:
                if keyword in search_text:
                    category_score += self.weights["weak"]
                    weight_total += self.weights["weak"]
                    matched_details[category].append(f"弱:{keyword}")
            
            # 🟢 修复评分逻辑 (Scoring Logic Fix)
            if weight_total > 0:
                # 获取当前类别的匹配列表
                current_matches = matched_details[category]  # ✅ 修复：使用正确的变量名
                match_count = len(current_matches)
                
                # 计算平均质量分 (3.0代表全都是强匹配)
                # 原始逻辑是除以 (weight_total * 3.0)，会导致分数极低
                # 现在改为：(总分 / 数量) / 3.0，这样强匹配就是 1.0
                average_score = category_score / match_count
                normalized_score = average_score / 3.0  
                
                # 数量激励：每多匹配一个词，增加 0.05 (上限 0.15)
                count_bonus = min(match_count * 0.05, 0.15)
                
                # 计算最终置信度
                confidence = min(normalized_score * 0.9 + count_bonus, 0.95)
                
                # 强关键词额外加成
                if any(k.startswith("强:") for k in current_matches):
                    confidence = min(confidence * 1.1, 0.98)
                
                scores[category] = round(confidence, 4)
        
        # 🟢 2. 工程排他性修正
        if any(ind in text_lower for ind in self.project_exclusive_indicators):
            scores["project"] = max(scores.get("project", 0), 0.82)
            matched_details["project"].append("排他特征:工程强相关")
            # 压制 goods
            if "goods" in scores: scores["goods"] = min(scores["goods"], 0.4)

        # 🟢 3. 服务优先权修正 (Service Dominant Logic)
        # 解决 "审计服务项目" 被误判为 "工程" 的问题
        if any(k in text_lower for k in self.service_dominant_keywords):
            scores["service"] = max(scores.get("service", 0), 0.85)
            matched_details["service"].append("排他特征:服务强相关")
            # 强行压制 project
            if "project" in scores: scores["project"] = min(scores["project"], 0.45)

        # 4. 兜底返回
        if not scores:
            return {
                "category": "goods", 
                "confidence": 0.4,
                "scores": {},
                "details": {"matched_keywords": [], "reason": "无关键词匹配"}
            }
        
        best_category = max(scores.items(), key=lambda x: x[1])
        
        return {
            "category": best_category[0],
            "confidence": best_category[1],
            "scores": dict(scores),
            "details": {
                "matched_keywords": matched_details[best_category[0]],
                "reason": f"匹配关键词: {len(matched_details[best_category[0]])}个"
            }
        }