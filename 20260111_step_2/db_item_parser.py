# db_item_parser.py
import re
from typing import Dict, List, Any, Tuple

def parse_db_items_strict(db_record: Dict[str, Any]) -> List[Dict[str, str]]:
    """
    严格解析DB字段，确保商品名称、参数、数量一一对应
    """
    # 提取并清理数组字段
    names = _clean_array_field(db_record.get("commodity_names"))
    params = _clean_array_field(db_record.get("parameter_requirements"))
    quantities = _clean_array_field(db_record.get("purchase_quantities"))
    brands = _clean_array_field(db_record.get("suggested_brands"))
    
    # 确定最大长度（确保数组对齐）
    max_len = max(len(names), len(params), len(quantities), len(brands))
    
    items = []
    for i in range(max_len):
        # 获取对应索引的值
        name = names[i] if i < len(names) else ""
        param = params[i] if i < len(params) else ""
        quantity = quantities[i] if i < len(quantities) else ""
        brand = brands[i] if i < len(brands) else ""
        
        # 跳过空商品名称
        if not name.strip():
            continue
            
        # 解析数量和单位
        qty_value, unit = _parse_quantity_unit(quantity, name)
        
        # 清理品牌信息
        brand_clean = "" if brand in ["-", "无", "无要求", "不限"] else brand
        
        item = {
            "商品名称": name.strip(),
            "规格型号": param.strip(),
            "建议品牌": brand_clean.strip(),
            "采购数量": qty_value,
            "单位": unit,
            "备注": ""
        }
        items.append(item)
    
    return items

def _clean_array_field(value: Any) -> List[str]:
    """清理数组字段，确保返回字符串列表"""
    if not value:
        return []
    if isinstance(value, list):
        return [str(x).strip() for x in value if x is not None and str(x).strip()]
    if isinstance(value, str):
        # 处理PostgreSQL数组格式 {item1,item2,item3}
        clean = value.strip()
        if clean.startswith('{') and clean.endswith('}'):
            clean = clean[1:-1]
        parts = [p.strip().strip('"').strip("'") for p in clean.split(',')]
        return [p for p in parts if p]
    return [str(value).strip()]

def _parse_quantity_unit(quantity_str: str, item_name: str) -> Tuple[str, str]:
    """智能解析数量和单位"""
    if not quantity_str:
        return "", "个"
    
    # 匹配模式：数字+单位
    match = re.search(r'(\d+)\s*([一-龥a-zA-Z]*)', str(quantity_str))
    if match:
        qty = match.group(1)
        raw_unit = match.group(2) or ""
        
        # 确定单位
        if raw_unit:
            unit = raw_unit
        else:
            # 根据商品名称智能推断单位
            unit = _infer_unit_from_name(item_name)
            
        return qty, unit
    
    return "", "个"

def _infer_unit_from_name(item_name: str) -> str:
    """根据商品名称推断单位"""
    name_lower = item_name.lower()
    
    if any(kw in name_lower for kw in ["桌椅", "套装", "组合", "套件"]):
        return "套"
    elif any(kw in name_lower for kw in ["柜", "箱", "架", "台"]):
        return "台"
    elif any(kw in name_lower for kw in ["椅", "凳", "把"]):
        return "把"
    elif any(kw in name_lower for kw in ["张", "床", "桌"]):
        return "张"
    elif any(kw in name_lower for kw in ["软件", "系统", "授权"]):
        return "套"
    elif any(kw in name_lower for kw in ["服务", "维护", "运维"]):
        return "项"
    else:
        return "个"
