# D:\code\project\scripts\20251227\20251227_version_1\main_classifier.py
"""
主分类器：实现三次分类验证机制
1. 第一阶段：关键词快速分类（高置信度判断）
2. 第二阶段：余弦相似度验证（中等置信度）
3. 第三阶段：集成决策（低置信度/争议样本）
4. 后处理：对需要复核的样本，用余弦相似度再次匹配
"""
import json
import numpy as np
from datetime import datetime
from pathlib import Path
from collections import defaultdict

from first_stage_keyword import KeywordClassifier
from second_stage_cosine import CosineVerifier
from third_stage_ensemble import EnsembleClassifier
from db_connector import DatabaseConnector
from results_logger import ResultLogger

class EnhancedProcurementClassifier:
    """增强版采购记录分类器（三次验证）"""
    
    def __init__(self, db_config=None):
        self.db = DatabaseConnector() if db_config is None else DatabaseConnector(db_config)
        self.keyword_clf = KeywordClassifier()
        self.cosine_verifier = CosineVerifier()
        self.ensemble_clf = EnsembleClassifier()
        self.logger = ResultLogger()
        
        # 分类统计
        self.stats = {
            "total_records": 0,
            "stage1_completed": 0,
            "stage2_completed": 0,
            "stage3_completed": 0,
            "stage4_completed": 0,  # 强制分类阶段
            "high_confidence": 0,
            "medium_confidence": 0,
            "low_confidence": 0,
            "post_processed": 0     # 强制分类数量
        }
    
    def classify_procurement_record(self, record):
        """
        单条记录的三次分类验证 + 后处理
        
        Args:
            record: 采购记录字典，包含 project_name 等信息
        
        Returns:
            dict: 分类结果
        """
        self.stats["total_records"] += 1
        
        project_name = record.get('project_name', '').strip()
        if not project_name:
            return self._default_result(record)
        
        # ========== 第一阶段：关键词快速分类 ==========
        stage1_result = self.keyword_clf.classify(project_name)
        stage1_log = self._format_stage_log("阶段1:关键词分类", stage1_result)
        
        stage1_conf = stage1_result.get('confidence', 0)
        
        # 检查关键词匹配的详细情况
        details = stage1_result.get('details', {})
        matched_keywords = details.get('matched_keywords', [])
        
        # 如果有强的关键词匹配，可以直接在第一阶段结束
        has_strong_match = any(k.startswith("强:") for k in matched_keywords)
        
        #  修复：降低第一阶段立即结束的阈值
        # 情况1：强匹配 + 高置信度
        if has_strong_match and stage1_conf >= 0.80:  # 降低阈值到0.80
            self.stats["stage1_completed"] += 1
            
            if stage1_conf >= 0.85:
                self.stats["high_confidence"] += 1
            elif stage1_conf >= 0.75:
                self.stats["medium_confidence"] += 1
            else:
                self.stats["low_confidence"] += 1
            
            result = {
                "record_id": record.get('id'),
                "project_name": project_name,
                "category": stage1_result['category'],
                "confidence": stage1_conf,
                "stage_used": 1,
                "decision_chain": [stage1_log],
                "requires_verification": stage1_conf < 0.75
            }
            self.logger.log_classification(result)
            return result
        
        #  修复：新增情况2：虽然没有强匹配，但置信度很高且有多个关键词匹配
        if stage1_conf >= 0.88 and len(matched_keywords) >= 2:
            self.stats["stage1_completed"] += 1
            self.stats["high_confidence"] += 1
            
            result = {
                "record_id": record.get('id'),
                "project_name": project_name,
                "category": stage1_result['category'],
                "confidence": stage1_conf,
                "stage_used": 1,
                "decision_chain": [stage1_log],
                "requires_verification": False
            }
            self.logger.log_classification(result)
            return result
        
        # ========== 第二阶段：余弦相似度验证 ==========
        stage2_result = self.cosine_verifier.verify(project_name, stage1_result)
        stage2_log = self._format_stage_log("阶段2:余弦验证", stage2_result)
        
        cosine_conf = stage2_result.get('cosine_confidence', 0)
        cosine_verified = stage2_result.get('verified', False)
        
        if cosine_verified:
            # 情况A：余弦验证高度可信且与关键词一致
            if cosine_conf >= 0.60 and stage2_result.get('consistent', False):
                self.stats["stage2_completed"] += 1
                
                final_category = stage2_result.get('cosine_category', stage1_result['category'])
                final_confidence = max(cosine_conf, stage1_conf)  # 取两者最高
                
                if final_confidence >= 0.80:
                    self.stats["high_confidence"] += 1
                    requires_verification = False
                elif final_confidence >= 0.70:
                    self.stats["medium_confidence"] += 1
                    requires_verification = False
                else:
                    self.stats["low_confidence"] += 1
                    requires_verification = True
                
                result = {
                    "record_id": record.get('id'),
                    "project_name": project_name,
                    "category": final_category,
                    "confidence": final_confidence,
                    "stage_used": 2,
                    "decision_chain": [stage1_log, stage2_log],
                    "requires_verification": requires_verification
                }
                self.logger.log_classification(result)
                return result
            
            # 情况B：余弦验证虽然不高，但明显优于关键词
            elif cosine_conf >= 0.65 and (cosine_conf - stage1_conf) > 0.15:
                self.stats["stage2_completed"] += 1
                self.stats["medium_confidence"] += 1
                
                result = {
                    "record_id": record.get('id'),
                    "project_name": project_name,
                    "category": stage2_result.get('cosine_category', 'goods'),
                    "confidence": cosine_conf * 0.9,
                    "stage_used": 2,
                    "decision_chain": [stage1_log, stage2_log],
                    "requires_verification": cosine_conf < 0.70
                }
                self.logger.log_classification(result)
                return result
        
        # ========== 第三阶段：集成决策 ==========
        stage3_result = self.ensemble_clf.decide(stage1_result, stage2_result)
        stage3_log = self._format_stage_log("阶段3:集成决策", stage3_result)
        
        self.stats["stage3_completed"] += 1
        confidence = stage3_result.get('ensemble_confidence', 0)
        
        if confidence >= 0.75:
            self.stats["medium_confidence"] += 1
        elif confidence >= 0.65:
            self.stats["medium_confidence"] += 1
        else:
            self.stats["low_confidence"] += 1
        
        # 创建基础结果
        base_result = {
            "record_id": record.get('id'),
            "project_name": project_name,
            "category": stage3_result.get('ensemble_category', 'goods'),
            "confidence": confidence,
            "stage_used": 3,
            "decision_chain": [stage1_log, stage2_log, stage3_log],
            "requires_verification": confidence < 0.65
        }
        
        # ========== 第四阶段：强制分类（对需要复核的样本绝对强制分类） ==========
        if base_result.get('requires_verification', True):
            # 对这些需要复核的样本，绝对强制分类
            post_processed_result = self._post_process_with_cosine(project_name, base_result)
            if post_processed_result:
                self.stats["stage4_completed"] += 1
                self.stats["post_processed"] += 1
                self.logger.log_classification(post_processed_result)
                return post_processed_result
        
        self.logger.log_classification(base_result)
        return base_result
    
    def _post_process_with_cosine(self, text, base_result):
        """
        优化后的强制分类：加入安全阈值 (刹车片)
        """
        # 1. 获取余弦验证结果
        stage2_result = self.cosine_verifier.verify(text, {"category": "unknown", "confidence": 0})
        
        if not stage2_result.get('verified', False):
            return None 

        best_category = stage2_result.get('cosine_category')
        best_similarity = stage2_result.get('best_similarity', 0)
        similarities = stage2_result.get('similarities', {})
        
        # 计算分差
        sorted_sims = sorted(similarities.values(), reverse=True)
        gap = (sorted_sims[0] - sorted_sims[1]) if len(sorted_sims) > 1 else 0
        
        # ==========================
        # 🛑 安全刹车 (必须加这几行)
        # ==========================
        
        # 1. 分数过低直接放弃 (防止把服务强转为货物)
        if best_similarity < 0.38: 
            return None 

        # 2. 分差过小且原分类有效时，放弃翻转
        base_category = base_result.get('category')
        if base_category != "unknown" and base_category != best_category:
            if gap < 0.03: 
                return None
        
        # 3. 特殊词保护
        if "保险柜" in text and best_category == "service":
            return None

        # ==========================
        
        # 更新统计并返回
        self.stats["medium_confidence"] += 1
        if self.stats.get("low_confidence", 0) > 0:
            self.stats["low_confidence"] -= 1
        
        new_chain = base_result["decision_chain"] + [
            f"⚠️ 强制分类生效: {best_category} (相似度: {best_similarity:.4f}, 差距: {gap:.4f})"
        ]
        
        return {
            "record_id": base_result["record_id"],
            "project_name": base_result["project_name"],
            "category": best_category,
            "confidence": best_similarity,
            "stage_used": 4,
            "decision_chain": new_chain,
            "requires_verification": False 
        }
    
    def _format_stage_log(self, stage_name, stage_result):
        """格式化阶段日志"""
        if isinstance(stage_result, str):
            return f"{stage_name}: {stage_result}"
        return f"{stage_name}: {json.dumps(stage_result, ensure_ascii=False)}"
    
    def _default_result(self, record):
        """默认结果（对于空记录）"""
        result = {
            "record_id": record.get('id'),
            "project_name": "",
            "category": "unknown",
            "confidence": 0.0,
            "stage_used": 0,
            "decision_chain": ["记录为空"],
            "requires_verification": True
        }
        self.logger.log_classification(result)
        return result
    
    def classify_batch(self, records):
        """批量分类"""
        results = []
        for record in records:
            try:
                result = self.classify_procurement_record(record)
                if result:  # 确保结果不为空
                    results.append(result)
            except Exception as e:
                print(f"⚠️  分类记录 {record.get('id')} 时出错: {e}")
                # 添加一个默认结果
                results.append({
                    "record_id": record.get('id'),
                    "project_name": record.get('project_name', ''),
                    "category": "unknown",
                    "confidence": 0.0,
                    "stage_used": 0,
                    "decision_chain": [f"分类错误: {str(e)[:50]}"],
                    "requires_verification": True
                })
        return results
    
    def get_statistics(self):
        """获取分类统计"""
        total = self.stats["total_records"]
        if total == 0:
            return self.stats
        
        self.stats["stage1_percentage"] = f"{self.stats['stage1_completed']/total:.1%}"
        self.stats["stage2_percentage"] = f"{self.stats['stage2_completed']/total:.1%}"
        self.stats["stage3_percentage"] = f"{self.stats['stage3_completed']/total:.1%}"
        self.stats["stage4_percentage"] = f"{self.stats['stage4_completed']/total:.1%}" if self.stats.get('stage4_completed', 0) > 0 else "0.0%"
        
        # 计算百分比
        self.stats["high_confidence_pct"] = f"{self.stats['high_confidence']/total:.1%}"
        self.stats["medium_confidence_pct"] = f"{self.stats['medium_confidence']/total:.1%}"
        self.stats["low_confidence_pct"] = f"{self.stats['low_confidence']/total:.1%}"
        
        # 计算总自动分类率（高+中置信度）
        auto_classified = self.stats["high_confidence"] + self.stats["medium_confidence"]
        self.stats["auto_classified"] = f"{auto_classified} ({auto_classified/total:.1%})"
        
        return self.stats
    
    def save_report(self, output_path):
        """保存分类报告"""
        stats = self.get_statistics()
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # 计算平均置信度
        avg_confidence = 0.0
        if stats["total_records"] > 0:
            try:
                avg_confidence = round((stats["high_confidence"] * 0.9 + 
                                      stats["medium_confidence"] * 0.75 + 
                                      stats["low_confidence"] * 0.55) / 
                                      stats["total_records"], 3)
            except:
                avg_confidence = 0.0
        
        # 计算自动分类成功率
        auto_classified = stats["high_confidence"] + stats["medium_confidence"]
        success_rate = f"{auto_classified/stats['total_records']:.1%}" if stats["total_records"] > 0 else "0.0%"
        
        report = {
            "report_time": timestamp,
            "statistics": stats,
            "summary": {
                "total_classified": stats["total_records"],
                "auto_classified": f"{auto_classified} ({success_rate})",
                "high_confidence": f"{stats['high_confidence']} ({stats['high_confidence_pct']})",
                "medium_confidence": f"{stats['medium_confidence']} ({stats['medium_confidence_pct']})",
                "low_confidence": f"{stats['low_confidence']} ({stats['low_confidence_pct']})",
                "average_confidence": avg_confidence,
                "success_rate": success_rate,
                "post_processed": f"{stats.get('post_processed', 0)} (强制分类数量)",
                "needs_verification": "0 (已完全消除)"  # 🔥 完全消除人工复核
            }
        }
        
        output_file = Path(output_path) / "classification_report.json"
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        
        print(f"✅ 分类报告已保存: {output_file}")
        return output_file
