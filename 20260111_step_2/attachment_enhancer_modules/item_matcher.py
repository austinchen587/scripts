# attachment_enhancer_modules/item_matcher.py
import re
from typing import List, Dict, Tuple, Optional
from .utils import calculate_similarity, calculate_string_similarity  # 导入两个函数


def find_matching_attachment_item(db_name: str, table_items: List[Tuple]) -> Tuple[str, str]:
    """在附件项目中寻找与DB名称匹配的项目"""
    db_name_clean = re.sub(r'[^\w\u4e00-\u9fa5]', '', db_name.lower())
    
    for att_name, att_qty, att_unit in table_items:
        att_name_clean = re.sub(r'[^\w\u4e00-\u9fa5]', '', att_name.lower())
        
        # 简单相似度匹配
        if (db_name_clean in att_name_clean or 
            att_name_clean in db_name_clean or
            calculate_similarity(db_name_clean, att_name_clean) > 0.6):
            return att_qty, att_unit or "个"
    
    return "", ""


def find_printer_item_match(db_name: str, parsed_items: List[Dict]) -> Optional[Dict]:
    """在解析项目中找到匹配项"""
    if not db_name or not parsed_items:
        return None
    
    db_name_norm = db_name.lower().replace(" ", "")
    
    # 先尝试精确匹配或包含匹配
    for item in parsed_items:
        item_name = item.get("商品名称", "").lower()
        
        if (db_name_norm == item_name or 
            db_name_norm in item_name or 
            item_name in db_name_norm):
            return item
        
        # 检查商品类别匹配
        db_keywords = ["硒鼓", "粉盒", "碳粉", "硬盘", "U盘", "鼠标"]
        for keyword in db_keywords:
            if keyword in db_name and keyword in item_name:
                return item
    
    # 相似度匹配
    best_match = None
    best_score = 0
    
    for item in parsed_items:
        item_name = item.get("商品名称", "")
        # 使用 available_similarity_function 避免函数名错误
        similarity_func = calculate_string_similarity if hasattr(calculate_string_similarity, '__call__') else calculate_similarity
        score = similarity_func(db_name, item_name)
        if score > best_score and score > 0.4:
            best_score = score
            best_match = item
    
    return best_match


def is_continuation_row(line: str) -> bool:
    """判断是否为续行（不包含序号）"""
    return not re.match(r'^\d+[\.、\s]', line)


def is_quantity_only_line(line: str) -> bool:
    """判断是否为只有数量的行"""
    return bool(re.match(r'^[\s]*\d+\s*([个支盒]?)$', line.strip()))
