# D:\code\project\scripts\20251227\20251227_version_1\results_logger.py
"""
结果记录器
"""

import json
from datetime import datetime
from pathlib import Path

class ResultLogger:
    """结果记录器"""
    
    def __init__(self, log_dir=None):
        self.log_dir = Path(log_dir) if log_dir else Path(__file__).parent / "logs"
        self.log_dir.mkdir(exist_ok=True)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.log_file = self.log_dir / f"classification_log_{timestamp}.txt"
        self.json_file = self.log_dir / f"classification_results_{timestamp}.json"
        
        self.all_results = []
        self.summary = {
            "start_time": timestamp,
            "total_processed": 0,
            "categories": {},
            "confidences": []
        }
    
    def log_classification(self, result):
        """记录单条分类结果"""
        self.all_results.append(result)
        self.summary["total_processed"] += 1
        
        # 更新类别统计
        category = result.get("category", "unknown")
        self.summary["categories"][category] = self.summary["categories"].get(category, 0) + 1
        
        # 更新置信度分布
        confidence = result.get("confidence", 0)
        self.summary["confidences"].append(confidence)
    
    def save_logs(self):
        """保存所有日志"""
        self._save_text_log()
        self._save_json_log()
        self._save_summary()
        
        return self.log_file, self.json_file
    
    def _save_text_log(self):
        """保存文本日志"""
        with open(self.log_file, 'w', encoding='utf-8') as f:
            f.write("=" * 80 + "\n")
            f.write("采购记录增强分类日志\n")
            f.write(f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write("=" * 80 + "\n\n")
            
            for i, result in enumerate(self.all_results):
                f.write(f"记录 #{i+1}\n")
                f.write(f"  ID: {result.get('record_id', 'N/A')}\n")
                f.write(f"  项目名称: {result.get('project_name', '')}\n")
                f.write(f"  分类结果: {result.get('category', 'unknown')}\n")
                f.write(f"  置信度: {result.get('confidence', 0):.4f}\n")
                f.write(f"  使用阶段: 阶段{result.get('stage_used', 0)}\n")
                f.write(f"  需要复核: {'是' if result.get('requires_verification', True) else '否'}\n")
                
                # 写入决策链
                decision_chain = result.get("decision_chain", [])
                if decision_chain:
                    f.write(f"  决策链:\n")
                    for j, decision in enumerate(decision_chain):
                        f.write(f"    步骤{j+1}: {decision}\n")
                
                f.write("-" * 60 + "\n")
    
    def _save_json_log(self):
        """保存JSON格式日志"""
        log_data = {
            "timestamp": datetime.now().isoformat(),
            "total_results": len(self.all_results),
            "results": self.all_results
        }
        
        with open(self.json_file, 'w', encoding='utf-8') as f:
            json.dump(log_data, f, ensure_ascii=False, indent=2)
    
    def _save_summary(self):
        """保存摘要"""
        import numpy as np
        
        if self.summary["confidences"]:
            confidences = self.summary["confidences"]
            avg_confidence = np.mean(confidences)
            min_confidence = np.min(confidences)
            max_confidence = np.max(confidences)
        else:
            avg_confidence = min_confidence = max_confidence = 0
        
        summary_file = self.log_dir / "classification_summary.txt"
        with open(summary_file, 'w', encoding='utf-8') as f:
            f.write("分类摘要报告\n")
            f.write("=" * 50 + "\n\n")
            f.write(f"处理时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"总处理记录: {self.summary['total_processed']}\n\n")
            
            f.write("类别分布:\n")
            for category, count in self.summary["categories"].items():
                percentage = count / self.summary["total_processed"] * 100
                f.write(f"  {category}: {count} 个 ({percentage:.1f}%)\n")
            
            f.write(f"\n置信度统计:\n")
            f.write(f"  平均置信度: {avg_confidence:.4f}\n")
            f.write(f"  最低置信度: {min_confidence:.4f}\n")
            f.write(f"  最高置信度: {max_confidence:.4f}\n")
            
            # 置信度分布
            bins = [(0, 0.6), (0.6, 0.7), (0.7, 0.8), (0.8, 0.9), (0.9, 1.0)]
            f.write(f"\n置信度分布:\n")
            for low, high in bins:
                count = sum(1 for c in confidences if low <= c < high)
                percentage = count / len(confidences) * 100 if confidences else 0
                bar = "█" * int(percentage / 2)
                f.write(f"  {low:.1f}-{high:.1f}: {count:3d} 个 ({percentage:5.1f}%) {bar}\n")
