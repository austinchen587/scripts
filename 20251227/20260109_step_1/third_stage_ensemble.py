# D:\code\project\scripts\20251227\20251227_version_1\third_stage_ensemble.py
"""
第三阶段：集成决策器
综合前两个阶段的结果做最终判断
"""

import numpy as np

class EnsembleClassifier:
    """集成决策器"""
    
    def __init__(self):
        # 决策规则
        self.decision_rules = [
            self._rule_high_confidence_agreement,
            self._rule_moderate_agreement,
            self._rule_cosine_dominates,
            self._rule_keyword_dominates,
            self._rule_tie_breaker
        ]
    
    def decide(self, keyword_result, cosine_result):
        """
        集成决策
        
        Args:
            keyword_result: 关键词分类结果
            cosine_result: 余弦验证结果
        
        Returns:
            dict: 集成决策结果
        """
        if not cosine_result.get("verified", False):
            # 余弦验证失败，使用关键词结果
            return {
                "ensemble_category": keyword_result.get("category", "goods"),
                "ensemble_confidence": keyword_result.get("confidence", 0.5) * 0.9,  # 降低置信度
                "decision_reason": "余弦验证失败，依赖关键词",
                "final_stage": "keyword_fallback"
            }
        
        # 应用决策规则
        for rule_func in self.decision_rules:
            result = rule_func(keyword_result, cosine_result)
            if result is not None:
                return result
        
        # 默认规则
        return self._rule_default(keyword_result, cosine_result)
    
    def _rule_high_confidence_agreement(self, kw, cos):
        """规则1：高置信度一致"""
        kw_conf = kw.get("confidence", 0)
        cos_conf = cos.get("cosine_confidence", 0)
        kw_cat = kw.get("category", "")
        cos_cat = cos.get("cosine_category", "")
        
        # 两者都高置信度且一致
        if kw_conf >= 0.85 and cos_conf >= 0.80 and kw_cat == cos_cat:
            final_conf = (kw_conf * 0.4 + cos_conf * 0.6)
            return {
                "ensemble_category": kw_cat,
                "ensemble_confidence": min(final_conf * 1.05, 0.98),
                "decision_reason": "关键词和余弦高置信度一致",
                "final_stage": "high_confidence_agreement"
            }
        return None
    
    def _rule_moderate_agreement(self, kw, cos):
        """规则2：中等置信度一致"""
        kw_conf = kw.get("confidence", 0)
        cos_conf = cos.get("cosine_confidence", 0)
        kw_cat = kw.get("category", "")
        cos_cat = cos.get("cosine_category", "")
        
        # 🔧 修复：降低一致性的要求
        if kw_cat == cos_cat:
            # 一致时，取两者平均值并适当提升
            avg_conf = (kw_conf + cos_conf) / 2
            final_conf = min(avg_conf * 1.1, 0.9)
            return {
                "ensemble_category": kw_cat,
                "ensemble_confidence": round(final_conf, 4),
                "decision_reason": "关键词和余弦类别一致",
                "final_stage": "moderate_agreement"
            }
        return None
    
    def _rule_cosine_dominates(self, kw, cos):
        """规则3：余弦相似度占主导"""
        kw_conf = kw.get("confidence", 0)
        cos_conf = cos.get("cosine_confidence", 0)
        cos_cat = cos.get("cosine_category", "")
        
        # 余弦相似度很高且明显高于关键词
        if cos_conf >= 0.85 and cos_conf - kw_conf >= 0.15:
            return {
                "ensemble_category": cos_cat,
                "ensemble_confidence": cos_conf,
                "decision_reason": "余弦相似度高度可信",
                "final_stage": "cosine_dominates"
            }
        return None
    
    def _rule_keyword_dominates(self, kw, cos):
        """规则4：关键词占主导"""
        kw_conf = kw.get("confidence", 0)
        cos_conf = cos.get("cosine_confidence", 0)
        kw_cat = kw.get("category", "")
        
        # 关键词置信度很高且明显高于余弦
        if kw_conf >= 0.90 and kw_conf - cos_conf >= 0.2:
            return {
                "ensemble_category": kw_cat,
                "ensemble_confidence": kw_conf * 0.95,
                "decision_reason": "关键词高度可信",
                "final_stage": "keyword_dominates"
            }
        return None
    
    def _rule_tie_breaker(self, kw, cos):
        """规则5：平局决胜"""
        kw_conf = kw.get("confidence", 0)
        cos_conf = cos.get("cosine_confidence", 0)
        kw_cat = kw.get("category", "")
        cos_cat = cos.get("cosine_category", "")
        
        # 类别不一致，置信度接近
        if kw_cat != cos_cat and abs(kw_conf - cos_conf) < 0.1:
            # 使用置信度加权平均
            total_conf = kw_conf + cos_conf
            kw_weight = kw_conf / total_conf
            cos_weight = cos_conf / total_conf
            
            # 偏向语义相似度（余弦相似度通常更可靠）
            if cos_weight > 0.55:
                final_cat = cos_cat
                final_conf = cos_conf * 0.9
                reason = "语义相似度略优"
            else:
                final_cat = kw_cat
                final_conf = kw_conf * 0.9
                reason = "关键词略优"
            
            return {
                "ensemble_category": final_cat,
                "ensemble_confidence": round(final_conf, 4),
                "decision_reason": f"置信度接近，{reason}",
                "final_stage": "tie_breaker"
            }
        return None
    
    def _rule_default(self, kw, cos):
        """默认规则"""
        kw_conf = kw.get("confidence", 0)
        cos_conf = cos.get("cosine_confidence", 0)
        
        # 选择置信度高的
        if cos_conf > kw_conf:
            return {
                "ensemble_category": cos.get("cosine_category", "goods"),
                "ensemble_confidence": cos_conf * 0.9,
                "decision_reason": "余弦相似度略高",
                "final_stage": "default_cosine"
            }
        else:
            return {
                "ensemble_category": kw.get("category", "goods"),
                "ensemble_confidence": kw_conf * 0.9,
                "decision_reason": "关键词置信度略高",
                "final_stage": "default_keyword"
            }
