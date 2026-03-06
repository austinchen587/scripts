# attachment_enhancer_modules/__init__.py
"""
附件增强器模块包
提供从附件文本中提取和增强商品信息的功能
"""

from .main import (
    enhance_with_attachment,
    clean_brand_field,
    enhance_with_attachment_optimized,
    enhance_with_attachment_comprehensive
)

__version__ = "1.0.0"
__all__ = [
    "enhance_with_attachment",
    "clean_brand_field",
    "enhance_with_attachment_optimized",
    "enhance_with_attachment_comprehensive"
]
