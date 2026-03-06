# attachment_enhancer.py（主文件，在项目根目录）
"""
附件增强器 - 对外接口文件
保持与原有代码的兼容性，内部调用模块化的代码
"""

from attachment_enhancer_modules import (
    enhance_with_attachment,
    clean_brand_field,
    enhance_with_attachment_optimized,
    enhance_with_attachment_comprehensive
)

# 导出所有函数
__all__ = [
    "enhance_with_attachment",
    "clean_brand_field",
    "enhance_with_attachment_optimized",
    "enhance_with_attachment_comprehensive"
]
