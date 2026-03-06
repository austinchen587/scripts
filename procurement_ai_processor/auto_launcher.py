import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

try:
    from processor import BrandProcessor

    def run_analysis():
        print(">>> [Step 3] 启动平台与搜索词分析...")
        processor = None
        try:
            processor = BrandProcessor()
            processor.process_all()
        except Exception as e:
            print(f">>> [Step 3] 异常: {e}")
        finally:
            if processor:
                processor.close()

    if __name__ == "__main__":
        run_analysis()
except Exception as e:
    print(f"FATAL ERROR in Step 3 Launcher: {e}")