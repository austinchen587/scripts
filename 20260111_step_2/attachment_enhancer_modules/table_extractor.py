# attachment_enhancer_modules/table_extractor.py
import re
from typing import List, Dict, Tuple, Optional
from .utils import infer_unit_from_name, clean_item_name, extract_specifications_from_line


def extract_table_items(text: str) -> List[Tuple[str, str, str]]:
    """从附件文本中提取表格形式的商品信息"""
    items = []
    
    # 表格模式：序号 商品名称 数量单价
    patterns = [
        r'(\d+)\s+([^\d\n]{2,20}?)\s+(\d+[\.\d]*)\s*([\u4e00-\u9fa5a-zA-Z]{1,2})?\s*\d+',
        r'商品[：:]?\s*([^\d\n]{2,20}?)\s+数量[：:]?\s*(\d+[\.\d]*)\s*([\u4e00-\u9fa5a-zA-Z]{1,2})?'
    ]
    
    for pattern in patterns:
        matches = re.findall(pattern, text)
        for match in matches:
            if len(match) >= 3:
                if len(match) == 4:  # 序号 名称 数量 单位
                    name, qty, unit = match[1], match[2], match[3]
                else:  # 名称 数量 单位
                    name, qty, unit = match[0], match[1], match[2]
                
                if name.strip() and qty.strip():
                    items.append((name.strip(), qty.strip(), unit.strip()))
    
    return items


def extract_detailed_procurement_table(attachment_text: str) -> List[Dict]:
    """
    增强：专门提取采购表格数据（支持规格列捕获）
    """
    items = []
    lines = attachment_text.split('\n')
    
    for line in lines:
        line = line.strip()
        if not line:
            continue
            
        # 跳过标题行
        if re.search(r'(序号|物资名称|商品名称|规格型号|采购数量|数量|单位|单价|金额|备注)', line):
            continue
        
        # 只要行里有数字，就尝试提取
        if re.search(r'\d', line):
            item_info = extract_procurement_item_from_line(line)
            if item_info:
                items.append(item_info)
    
    return items  # 直接返回，不再回退到旧逻辑，因为旧逻辑会丢失规格


def extract_procurement_item_from_line(line: str) -> Optional[Dict]:
    """
    从单行中提取采购项信息 - 核心正则优化
    目标：提取 [商品名] ... [规格型号(可能很长)] ... [数量] [单位]
    """
    line_clean = re.sub(r'\s+', ' ', line.strip()) # 压缩空格
    
    # === 优化后的正则策略 ===
    
    # 模式A：Markdown表格行 ( | 序号 | 名称 | 规格 | 数量 | )
    # 假设列顺序通常是 名称在前，数量在后
    if '|' in line_clean:
        parts = [p.strip() for p in line_clean.split('|') if p.strip()]
        if len(parts) >= 3:
            # 启发式查找：找包含数字的列作为数量，其左边可能是规格，再左边是名称
            # 这里简化处理，配合LLM使用，正则只做兜底
            pass 

    # 模式B：通用文本行 (最常见的扫描件OCR结果)
    # 逻辑：捕获开头非数字部分(名)，捕获中间任意部分(规格)，捕获末尾数字(量)
    
    # Regex解释：
    # 1. (?:^\d+[\.\s]*)? -> 忽略开头的序号 "1." 或 "1 "
    # 2. ([^\d\s][^×\d]{1,15}?) -> 商品名：非数字开头，长度2-15，非贪婪
    # 3. \s+ -> 空格分隔
    # 4. (.*?) -> 规格型号：中间的核心捕捉区，非贪婪
    # 5. \s+ -> 空格分隔
    # 6. (\d+) -> 数量
    # 7. \s*([个台套张把本项箱支组]?) -> 单位(可选)
    
    pattern_comprehensive = r'(?:^\d+[\.\s]*)?([^\d\s][^×\d]{1,15}?)\s+(.*?)\s+(\d+)\s*([个台套张把本项箱支组]?)'
    
    match = re.search(pattern_comprehensive, line_clean)
    
    # 验证匹配结果是否合理
    if match:
        name_candidate = match.group(1).strip()
        spec_candidate = match.group(2).strip()
        qty_candidate = match.group(3).strip()
        unit_candidate = match.group(4).strip()
        
        # 过滤误判：如果规格里全是数字或价格，可能提取错了
        if "元" in spec_candidate or "单价" in spec_candidate:
             # 尝试重新清洗spec_candidate，移除价格
             spec_candidate = re.sub(r'[\d\.]+\s*元.*', '', spec_candidate).strip()

        # 过滤误判：如果名称太长，可能把规格也吃进去了，需要LLM来救，这里只做基础提取
        if len(name_candidate) > 20: 
            return None 

        # 验证有效性
        if name_candidate and qty_candidate:
            return {
                "商品名称": clean_item_name(name_candidate),
                "规格型号": spec_candidate, # 重点：现在我们有了中间这一段
                "采购数量": qty_candidate,
                "单位": unit_candidate if unit_candidate else infer_unit_from_name(name_candidate),
                "来源": "正则通用增强"
            }

    # 回退：尝试简单的 "名称 数量" 模式（针对没有规格的行）
    pattern_simple = r'(?:^\d+[\.\s]*)?([^\d\s][^×\d]{1,20}?)\s+(\d+)\s*([个台套张把本项箱支组])'
    match_simple = re.search(pattern_simple, line_clean)
    if match_simple:
         return {
            "商品名称": clean_item_name(match_simple.group(1)),
            "规格型号": "", # 确实没抓到
            "采购数量": match_simple.group(2),
            "单位": match_simple.group(3),
            "来源": "正则简单提取"
        }

    return None


def convert_table_items_to_dict(table_items: List[Tuple]) -> List[Dict]:
    """将表格项目转换为字典格式"""
    result = []
    for name, qty, unit in table_items:
        result.append({
            "商品名称": name,
            "采购数量": qty,
            "单位": unit or infer_unit_from_name(name),
            "来源": "附件表格提取"
        })
    return result
