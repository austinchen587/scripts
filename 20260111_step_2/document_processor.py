# document_processor.py - 拆分后的模块入口文件
"""
文档处理器模块 - 拆分后的主入口
此文件作为向后兼容的包装器，将所有功能重定向到新的模块结构

外部调用完全不变：import document_processor
"""

import sys
from pathlib import Path


# 添加新模块目录到路径
current_dir = Path(__file__).parent
module_dir = current_dir / "document_processor"
if module_dir.exists():
    sys.path.insert(0, str(current_dir))

try:
    # 尝试从新模块导入
    from document_processor.core import (
        extract_text,
        extract_text_enhanced,
        extract_with_embedded_images
    )
    
    # 导入其他功能
    from document_processor.libreoffice_utils import office_to_pdf
    from document_processor.pdf_processor import (
        extract_text_native,
        pdf_to_images,
        extract_text_with_table_enhancement
    )
    from document_processor.ocr_processor import (
        extract_from_image_with_ollama,
        extract_text_from_image_ocr
    )
    from document_processor.config import (
        DOWNLOAD_DIR,
        LIBREOFFICE_PATH,
        POPPLER_BIN_PATH
    )
    
    # 导入图片提取器类
    from document_processor.image_extractor import (
        OfficeImageExtractor,
        image_extractor,
        extract_with_embedded_images
    )
    
    print("[DOC] ✅ 使用模块化版本的 document_processor")
    
except ImportError as e:
    print(f"[DOC] ⚠️ 模块导入失败: {e}")
    print("[DOC] ℹ️ 尝试使用备用方案...")
    
    # 如果新模块不存在，使用旧版代码（兼容性后备）
    # 这里可以直接复制旧版的核心函数，但建议优先修复模块导入问题
    def extract_text(file_path: str, project_name: str = "") -> str:
        """兼容性后备函数"""
        print("[DOC] ⚠️ 使用兼容性后备函数")
        return ""
    
    def extract_text_enhanced(file_path: str, project_name: str = "") -> str:
        """兼容性后备函数"""
        print("[DOC] ⚠️ 使用兼容性后备函数")
        return ""
    
    # 设置默认值
    DOWNLOAD_DIR = "/Users/austinchen587gmail.com/myenv/project/scripts/20251227/20260111_step_2/downloads"
    LIBREOFFICE_PATH = "soffice"
    POPPLER_BIN_PATH = None

# ============================================
# 版本信息和帮助函数
# ============================================

def get_version() -> str:
    """获取模块版本"""
    return "2.0.0 (模块化版本)"

def list_functions() -> list:
    """列出所有可用的函数"""
    functions = [
        "extract_text(file_path, project_name='') - 原始文档提取",
        "extract_text_enhanced(file_path, project_name='') - 增强文档提取（含图片识别）",
        "extract_with_embedded_images(file_path, project_name='') - 提取文档中的图片文字",
        "office_to_pdf(input_path) - Office转PDF",
        "extract_text_native(pdf_path) - 原生PDF文字提取",
        "pdf_to_images(pdf_path) - PDF转图片",
        "extract_text_with_table_enhancement(pdf_path) - 表格增强提取",
        "extract_from_image_with_ollama(image_path, project_name) - Ollama-VL图片识别",
        "extract_text_from_image_ocr(image_path) - 传统OCR识别"
    ]
    return functions

# ============================================
# 模块初始化
# ============================================

if __name__ == "__main__":
    # 模块测试
    print(f"文档处理器模块 v{get_version()}")
    print("=" * 50)
    print("可用函数:")
    for func in list_functions():
        print(f"  - {func}")
    print("=" * 50)
    print(f"配置:")
    print(f"  下载目录: {DOWNLOAD_DIR}")
    print(f"  LibreOffice路径: {LIBREOFFICE_PATH}")
    print(f"  Poppler路径: {POPPLER_BIN_PATH or '未设置'}")
    
    # 测试导入
    try:
        test_func = extract_text
        print(f"\n✅ 主函数导入成功: {test_func.__name__}")
    except:
        print("\n❌ 函数导入失败，请检查模块结构")
