"""
主程序入口
"""

import logging
import sys
from processor import BrandProcessor

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('procurement_processor.log', encoding='utf-8')
    ]
)

logger = logging.getLogger(__name__)

def main():
    """
    主函数 - 简化为调用处理器
    """
    processor = None
    
    try:
        # 创建处理器并执行处理
        processor = BrandProcessor()
        result = processor.process_all()
        return result
        
    except KeyboardInterrupt:
        print("\n⚠️  程序被用户中断")
        return {"success": False, "error": "用户中断"}
        
    except Exception as e:
        print(f"\n❌ 程序执行异常: {e}")
        return {"success": False, "error": str(e)}
        
    finally:
        # 清理资源
        if processor:
            processor.close()

if __name__ == "__main__":
    # 执行主程序
    main()
