# attachment_enhancer_modules/main.py
import re
from typing import List, Dict, Tuple, Optional

# 导入各个模块
from .utils import (
    clean_brand_field,
    is_better_quantity,
    calculate_string_similarity
)

from .table_extractor import (
    extract_table_items,
    extract_detailed_procurement_table
)

from .item_matcher import (
    find_matching_attachment_item
)

from .printer_module import (
    is_printer_consumables_table,
    enhance_printer_consumables_table
)


def enhance_with_attachment(db_items: List[Dict], attachment_text: str) -> List[Dict]:
    """
    使用附件文本增强DB解析结果（不是覆盖，是增强）
    """
    if not attachment_text or not db_items:
        return db_items
    
    enhanced_items = []
    
    # 从附件中提取表格信息
    table_items = extract_table_items(attachment_text)
    
    # 尝试将附件信息与DB项目匹配
    for db_item in db_items:
        enhanced_item = db_item.copy()
        db_name = db_item["商品名称"]
        
        # 寻找附件中的对应项目
        matched_attachment_item = find_matching_attachment_item(db_name, table_items)
        
        if matched_attachment_item:
            # 增强：使用附件的数量信息（如果更准确）
            att_qty, att_unit = matched_attachment_item
            if att_qty and is_better_quantity(att_qty, db_item["采购数量"]):
                enhanced_item["采购数量"] = att_qty
                enhanced_item["单位"] = att_unit
                enhanced_item["备注"] = "数量信息来自附件"
        
        enhanced_items.append(enhanced_item)
    
    return enhanced_items


def enhance_with_attachment_optimized(db_items: List[Dict], attachment_text: str) -> List[Dict]:
    """
    增强版的附件增强 - 先尝试提取详细表格，再增强原数据
    """
    if not attachment_text or not db_items:
        return db_items
    
    # 1. 尝试提取详细的表格数据
    detailed_items = extract_detailed_procurement_table(attachment_text)
    
    # 如果提取到详细的表格项，优先使用
    if detailed_items and len(detailed_items) > 1:
        print(f"[ENHANCE-OPT] ✅ 提取到 {len(detailed_items)} 个详细商品，优先使用")
        return detailed_items
    
    # 2. 否则使用原有的增强逻辑
    print(f"[ENHANCE-OPT] 🔄 使用原有增强逻辑")
    return enhance_with_attachment(db_items, attachment_text)


def enhance_with_attachment_comprehensive(db_items: List[Dict], attachment_text: str) -> List[Dict]:
    """
    综合增强函数 - 集成打印机耗材表处理
    """
    if not attachment_text or not db_items:
        return db_items
    
    # 1. 检查是否为打印机耗材表
    if is_printer_consumables_table(attachment_text):
        result = enhance_printer_consumables_table(db_items, attachment_text)
        if len(result) > max(len(db_items), 5):  # 如果有显著改善
            print(f"[COMPREHENSIVE] ✅ 使用打印机耗材表增强结果")
            return result
    
    # 2. 使用原有的增强逻辑
    print(f"[COMPREHENSIVE] 🔄 使用原有增强逻辑")
    return enhance_with_attachment_optimized(db_items, attachment_text)
