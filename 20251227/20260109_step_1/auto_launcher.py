import sys
import os

# 将当前目录加入路径，确保能导入模块
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

try:
    from run_full_classification import EnhancedDeduplicationClassifier
    
    def run_headless():
        print(">>> [Step 1] 启动自动分类...")
        edc = EnhancedDeduplicationClassifier()
        edc.initialize_processed_ids()
        
        # hours=None 表示处理所有未分类记录
        uncategorized = edc.fetch_uncategorized_records_with_deduplication(hours=None)
        
        if not uncategorized:
            print(">>> [Step 1] 没有新记录需要分类")
            return

        # 批量处理
        batch_size = 50
        for i in range(0, len(uncategorized), batch_size):
            batch = uncategorized[i:i+batch_size]
            print(f">>> 处理批次 {i//batch_size + 1}")
            
            batch_results = []
            for record in batch:
                try:
                    result = edc.classifier.classify_procurement_record(record)
                    if result: batch_results.append(result)
                except Exception as e:
                    print(f"错误: {e}")
            
            if batch_results:
                edc.save_results_with_verification(batch_results)
                
        print(">>> [Step 1] 分类完成")

    if __name__ == "__main__":
        run_headless()
except Exception as e:
    print(f"FATAL ERROR in Step 1 Launcher: {e}")