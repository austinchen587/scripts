# D:\code\project\scripts\20260111_step_2\auto_launcher.py
import sys
import os
import time
import io
import logging

# 【关键修复】强制标准输出使用 UTF-8，防止 Emoji 导致程序崩溃
if sys.stdout.encoding != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# 【关键配置】配置日志直接输出到控制台
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)

# 添加路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from main import ensure_ollama_gpu_server, wait_for_gpu_initialization
    from main_pipeline.main_controller import MainController

    def run_once():
        print(">>> [Step 2] 启动深度解析...")
        
        # 1. 确保 GPU 服务就绪
        ensure_ollama_gpu_server()
        wait_for_gpu_initialization()
        
        # 2. 实例化控制器
        # batch_size=10: 配合 SQL 的 LIMIT 10
        controller = MainController(batch_size=10, skip_processed=True, cleanup_files=True)
        
        try:
            # 【核心修改】这里必须传入 max_batches=1
            # 告诉控制器：只处理 1 个批次（即 10 条数据）就强制退出！
            print(f">>> 开始处理本批次任务 (Limit 10, Max Batches 1)...")
            controller.run(max_batches=1)
            
        except Exception as e:
            logging.error(f"处理过程中发生错误: {e}", exc_info=True)
            raise
        finally:
            # 确保关闭数据库连接
            if hasattr(controller, 'db_writer') and controller.db_writer:
                controller.db_writer.close()
            
        print(">>> [Step 2] 本次解析完成 (退出进程，返回总控)")

    if __name__ == "__main__":
        run_once()

except Exception as e:
    logging.error(f"FATAL ERROR in Step 2 Launcher: {e}", exc_info=True)