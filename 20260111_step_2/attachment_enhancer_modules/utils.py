# attachment_enhancer_modules/utils.py
import re
from typing import Tuple, List, Dict, Optional


def infer_unit_from_name(name: str) -> str:
    """根据商品名称推断单位"""
    unit_keywords = {
        "张": ["海报", "横幅", "奖状", "证书", "照片", "纸张", "画", "地图"],
        "个": ["徽章", "党徽", "标志", "饰品", "工艺品", "纪念品"],
        "本": ["笔记本", "手册", "书籍", "相册", "册子"],
        "套": ["书籍", "资料", "文具", "装备", "服装"],
        "件": ["衣服", "T恤", "马甲", "服装", "外套"],
        "把": ["雨伞", "伞", "工具"],
        "台": ["电脑", "打印机", "复印机", "设备"],
        "项": ["服务", "活动"],
        "批": ["物资", "用品"]
    }
    
    name_lower = name.lower()
    for unit, keywords in unit_keywords.items():
        if any(keyword in name_lower for keyword in keywords):
            return unit
    
    if "证书" in name:
        return "本"
    elif "奖状" in name:
        return "张"
    elif "宣传" in name or "海报" in name:
        return "张"
    
    return "个"


def calculate_similarity(str1: str, str2: str) -> float:
    """计算两个字符串的简单相似度"""
    if not str1 or not str2:
        return 0.0
    set1, set2 = set(str1), set(str2)
    intersection = len(set1 & set2)
    union = len(set1 | set2)
    return intersection / union if union > 0 else 0.0


def calculate_string_similarity(str1: str, str2: str) -> float:
    """计算字符串相似度（兼容性函数）"""
    return calculate_similarity(str1, str2)


def is_better_quantity(att_qty: str, db_qty: str) -> bool:
    """判断附件的数量信息是否更好"""
    if not db_qty:
        return True
    if att_qty.isdigit() and db_qty.isdigit():
        return int(att_qty) > 0  # 附件有具体数字就认为更好
    return len(att_qty) > len(db_qty)  # 非数字情况下长度更长认为更好


def clean_brand_field(brand_str: str) -> str:
    """清理品牌字段，提取主要品牌"""
    if not brand_str:
        return ""
    
    # 分割多个品牌
    brands = re.split(r'[/、,，]', brand_str)
    
    # 提取第一个有效品牌
    for brand in brands:
        brand_clean = brand.strip()
        if brand_clean and brand_clean not in ["无品牌", "无要求", "无特殊要求"]:
            return brand_clean
    
    return ""


def clean_item_name(name: str) -> str:
    """清理商品名称"""
    # 移除序号
    name = re.sub(r'^\d+[\.、]?\s*', '', name)
    # 移除价格信息
    name = re.sub(r'\s*\d+[\.\d]*\s*元.*$', '', name)
    # 移除括号中的备注
    name = re.sub(r'\s*\([^)]*定制[^)]*\)', '', name)
    # 移除"定制"及之后内容
    if "定制" in name:
        name = name.split("定制")[0].strip()
    
    return name.strip()


def extract_specifications_from_line(line: str, name: str) -> str:
    """从行中提取规格信息"""
    # 如果行中有括号，提取括号内容作为规格
    bracket_match = re.search(r'\(([^)]+)\)', line)
    if bracket_match:
        return bracket_match.group(1).strip()
    
    # 如果有"规格："、"型号："等关键词
    spec_keywords = ["规格", "型号", "尺寸", "规格型号"]
    for keyword in spec_keywords:
        if keyword + "：" in line or keyword + ":" in line:
            pattern = fr'{keyword}[：:]\s*([^，。;\s]+)'
            match = re.search(pattern, line)
            if match:
                return match.group(1)
    
    # 如果名称包含规格信息
    if "A3" in line.upper():
        return "A3尺寸"
    elif "A4" in line.upper():
        return "A4尺寸"
    
    return line.replace(name, "").strip()
