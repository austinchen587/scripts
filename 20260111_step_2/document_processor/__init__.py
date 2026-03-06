
"""
文档处理器模块 - 保持向后兼容
外部调用方式不变：import document_processor
"""

# 导入主函数，保持原有接口
from .core import extract_text, extract_text_enhanced, extract_with_embedded_images

# 可选：导出其他功能函数
from .libreoffice_utils import office_to_pdf
from .pdf_processor import extract_text_native, pdf_to_images, extract_text_with_table_enhancement
from .ocr_processor import extract_from_image_with_ollama, extract_text_from_image_ocr

# 保持模块级别的变量（如果需要）
from .config import LIBREOFFICE_PATH, POPPLER_BIN_PATH, DOWNLOAD_DIR

# 说明：外部代码仍然可以像以前一样调用 document_processor.extract_text()
