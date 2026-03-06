# attachment_enhancer_modules/printer_module.py
import re
from typing import List, Dict, Optional
from .utils import calculate_string_similarity


def is_printer_consumables_table(text: str) -> bool:
    """检测是否为打印机耗材采购表"""
    keywords = [
        "硒鼓", "粉盒", "碳粉", "鼓组件", "打印机", "打印耗材", 
        "打印机耗材", "复印机耗材", "耗材采购", "奔图", "HP",
        "联想", "兄弟", "理光", "东芝", "京瓷"
    ]
    
    found_count = sum(1 for keyword in keywords if keyword in text)
    return found_count >= 3  # 有3个以上关键词认为是打印机耗材表


def parse_printer_consumables_table(text: str) -> List[Dict]:
    """解析打印机耗材采购表"""
    items = []
    lines = text.split('\n')
    
    current_item = None
    in_table = False
    skip_count = 0
    
    for i, line in enumerate(lines):
        line = line.strip()
        
        # 检测表格开始
        if not in_table and any(keyword in line for keyword in ["序号", "品目", "规格、型号", "品牌、规格", "单位"]):
            if "数量" in line or "单价" in line:
                in_table = True
                print(f"[PRINTER-ENHANCE] 在第{i+1}行找到表格标题: {line}")
                skip_count = 1  # 跳过标题后的空行
                continue
        
        # 跳过标题后的空行
        if skip_count > 0:
            skip_count -= 1
            continue
        
        # 表格结束检测
        if in_table and any(line.startswith(keyword) for keyword in ["质量及服务要求", "备注", "合计", "总计", "总金额"]):
            print(f"[PRINTER-ENHANCE] 在第{i+1}行结束表格")
            break
        
        if not in_table:
            continue
        
        # 处理表格行
        item_info = parse_printer_table_line(line)
        
        if item_info:
            # 如果有未保存的条目且新条目不是上一条的延续，先保存
            if current_item and not is_continuation_row(line):
                items.append(current_item)
                current_item = item_info
            else:
                current_item = item_info
        else:
            # 尝试处理不完整的行
            if current_item and is_quantity_only_line(line):
                quantity_match = re.search(r'(\d+)\s*([个支盒]?)', line)
                if quantity_match:
                    qty, unit = quantity_match.groups()
                    current_item["采购数量"] = qty
                    current_item["单位"] = unit or "支"
                    items.append(current_item)
                    current_item = None
    
    # 保存最后一个条目
    if current_item:
        items.append(current_item)
    
    # 二次处理：尝试找到被遗漏的规格型号
    enhance_printer_specifications(items, text)
    
    return items


def parse_printer_table_line(line: str) -> Optional[Dict]:
    """解析打印机耗材表格的一行"""
    if not line or len(line) < 2:
        return None
    
    # 移除多余空格
    line_clean = re.sub(r'\s+', ' ', line.strip())
    
    # 模式1: 序号 品目 品牌规格型号 单位 数量
    pattern1 = r'^(\d+)[、.\s]*([^\d\s]{2,10}?)\s+([^\d]+?)\s+([个支盒吨])\s+(\d+)'
    match1 = re.match(pattern1, line_clean)
    
    if match1:
        seq, category, specs, unit, quantity = match1.groups()
        return {
            "商品名称": normalize_printer_item_name(category),
            "规格型号": extract_printer_specs(specs),
            "品牌": extract_printer_brand(specs),
            "打印机型号": extract_printer_model(specs),
            "采购数量": quantity,
            "单位": unit,
            "备注": "",
            "来源": "打印机耗材表"
        }
    
    # 模式2: 序号 规格型号 单位 数量
    pattern2 = r'^(\d+)[、.\s]*([^\d\s]+?)\s+([个支盒])\s+(\d+)'
    match2 = re.match(pattern2, line_clean)
    
    if match2:
        seq, specs, unit, quantity = match2.groups()
        item_name = infer_printer_item_from_specs(specs)
        return {
            "商品名称": item_name,
            "规格型号": extract_printer_specs(specs),
            "品牌": extract_printer_brand(specs),
            "打印机型号": extract_printer_model(specs),
            "采购数量": quantity,
            "单位": unit,
            "备注": "",
            "来源": "打印机耗材表"
        }
    
    # 模式3: 规格型号 + 斜杠分隔的详细信息
    if "/" in line_clean and (line_clean.endswith("支") or "含安装" in line_clean):
        parts = line_clean.split("/")
        specs = parts[0].strip()
        item_name = infer_printer_item_from_specs(specs)
        
        return {
            "商品名称": item_name,
            "规格型号": specs,
            "品牌": extract_printer_brand(specs),
            "打印机型号": extract_printer_model(specs),
            "采购数量": "1",  # 默认
            "单位": "支",
            "备注": "/".join(parts[1:3]) if len(parts) > 1 else "",
            "来源": "打印机耗材表"
        }
    
    return None


def normalize_printer_item_name(name: str) -> str:
    """标准化打印机耗材商品名称"""
    if not name:
        return "硒鼓"
    
    mappings = {
        "硒鼓": ["硒鼓", "鼓"],
        "粉盒": ["粉盒", "墨盒"],
        "碳粉": ["碳粉", "墨粉"],
        "鼓组件": ["鼓组件", "鼓架"],
        "显影组件": ["显影", "显影组件"],
        "硬盘": ["硬盘", "固态硬盘", "SSD"],
        "光盘": ["光盘", "DVD"],
        "鼠标": ["鼠标"],
        "U盘": ["U盘", "USB盘"],
        "适配器": ["适配器", "电源适配器"],
        "存储卡": ["存储卡", "SD卡", "TF卡"],
        "键盘": ["键盘"],
        "芯片": ["芯片"],
        "外设": ["HUB", "线", "连接线", "数据线"]
    }
    
    for standard_name, keywords in mappings.items():
        if any(keyword in name for keyword in keywords):
            return standard_name
    
    return name.strip()


def infer_printer_item_from_specs(specs: str) -> str:
    """从规格型号推断商品名称"""
    if not specs:
        return "耗材"
    
    if "硒鼓" in specs:
        return "硒鼓"
    elif "粉盒" in specs:
        return "粉盒"
    elif "碳粉" in specs:
        return "碳粉"
    elif "鼓组件" in specs or "鼓架" in specs:
        return "鼓组件"
    elif "显影" in specs:
        return "显影组件"
    elif "硬盘" in specs:
        return "硬盘"
    elif "DVD" in specs or "光盘" in specs:
        return "光盘"
    elif "鼠标" in specs:
        return "鼠标"
    elif "U盘" in specs or "USB" in specs:
        return "U盘"
    elif "键盘" in specs:
        return "键盘"
    elif "芯片" in specs:
        return "芯片"
    
    return "硒鼓"  # 默认


def extract_printer_specs(specs_text: str) -> str:
    """提取打印机耗材规格"""
    if not specs_text:
        return ""
    
    # 尝试提取品牌+型号
    brand_model_patterns = [
        r'(奔图[PpMm]?\d+[A-Z]*)',
        r'(HP[-\s]?[A-Z0-9]+[A-Z]*)',
        r'(联想[Ll][Jj]?\d+)',
        r'(兄弟[FfXx][-\s]?\d+)',
        r'(理光\d+)',
        r'(东芝\d+[AaCc])',
        r'(京瓷[KkTt][-\s]?\d+)',
        r'(爱国者\d+[Gg])',
        r'(雷柏[A-Z]?\d+)',
        r'(三星\d+[Gg])',
    ]
    
    for pattern in brand_model_patterns:
        match = re.search(pattern, specs_text)
        if match:
            return match.group(1)
    
    # 如果有"/"，取前面部分
    if "/" in specs_text:
        return specs_text.split("/")[0].strip()
    
    return specs_text.strip()


def extract_printer_brand(specs_text: str) -> str:
    """提取品牌"""
    brands = ["奔图", "HP", "惠普", "联想", "兄弟", "理光", "东芝", 
              "京瓷", "爱国者", "雷柏", "三星", "飞利浦"]
    
    for brand in brands:
        if brand in specs_text:
            return "惠普" if brand == "HP" else brand
    
    return ""


def extract_printer_model(specs_text: str) -> str:
    """提取打印机型号"""
    model_patterns = [
        r'P\d+[A-Z]*',  # 奔图P系列
        r'M\d+[A-Z]*',  # 奔图M系列
        r'\d+[A-Z]{2,3}',  # HP系列
        r'LJ\d+',  # 联想LJ系列
        r'FX-\d+',  # 兄弟FX系列
        r'\d+[ACac]{2}',  # 东芝2020AC等
        r'TK-\d+',  # 京瓷TK系列
    ]
    
    for pattern in model_patterns:
        match = re.search(pattern, specs_text)
        if match:
            return match.group(0)
    
    # 尝试提取数字型号
    match = re.search(r'\d{4,}', specs_text)
    return match.group(0) if match else ""


def enhance_printer_specifications(items: List[Dict], text: str):
    """增强规格型号信息"""
    # 从文本中查找可能的规格说明
    lines = text.split('\n')
    
    # 构建一个映射：关键词->规格说明
    spec_mapping = {}
    for line in lines:
        if "含安装" in line or "原装" in line or "调试" in line:
            parts = line.split("/")
            if len(parts) > 1:
                key = parts[0].strip()
                spec = "/".join(parts[1:]).strip()
                if key and spec:
                    spec_mapping[key] = spec
    
    # 应用到项目
    for item in items:
        specs = item.get("规格型号", "")
        if not item.get("备注") and specs in spec_mapping:
            item["备注"] = spec_mapping[specs]


def enhance_printer_consumables_table(db_items: List[Dict], attachment_text: str) -> List[Dict]:
    """
    专门处理打印机耗材采购表格（如昌吉州应急管理局的采购表）
    """
    if not attachment_text:
        return db_items
    
    # 检测是否为打印机耗材采购表
    if not is_printer_consumables_table(attachment_text):
        print(f"[PRINTER-ENHANCE] 未识别为打印机耗材表，跳过")
        return db_items
    
    print(f"[PRINTER-ENHANCE] 开始处理打印机耗材采购表")
    
    # 从附件中解析表格
    parsed_items = parse_printer_consumables_table(attachment_text)
    
    if not parsed_items:
        print(f"[PRINTER-ENHANCE] 未解析到有效商品")
        return db_items
    
    print(f"[PRINTER-ENHANCE] 解析到 {len(parsed_items)} 个耗材商品")
    
    # 如果DB只有一个项目但附件有很多项，使用附件结果替代
    if len(db_items) <= 1 and len(parsed_items) > 5:
        print(f"[PRINTER-ENHANCE] ✅ 附件有详细数据，替代原结果")
        return parsed_items
    
    # 否则合并增强
    enhanced_items = []
    
    # 先将DB项目按附件信息增强
    for db_item in db_items:
        enhanced = db_item.copy()
        db_name = enhanced.get("商品名称", "")
        
        # 在附件中查找匹配项
        matched_item = find_printer_item_match(db_name, parsed_items)
        
        if matched_item:
            # 合并信息
            enhanced.update({
                "规格型号": matched_item.get("规格型号", enhanced.get("规格型号", "")),
                "采购数量": matched_item.get("采购数量", enhanced.get("采购数量", "1")),
                "单位": matched_item.get("单位", enhanced.get("单位", "支")),
                "品牌": matched_item.get("品牌", ""),
                "打印机型号": matched_item.get("打印机型号", ""),
                "备注": "信息来自附件详细表格"
            })
        
        enhanced_items.append(enhanced)
    
    # 添加附件中额外的项目
    added_counter = 0
    for item in parsed_items:
        item_name = item.get("商品名称", "")
        # 检查是否已存在
        exists = False
        for enhanced_item in enhanced_items:
            if item_name in enhanced_item.get("商品名称", "") or enhanced_item.get("商品名称", "") in item_name:
                exists = True
                break
        
        if not exists:
            enhanced_items.append(item)
            added_counter += 1
    
    if added_counter > 0:
        print(f"[PRINTER-ENHANCE] 新增 {added_counter} 个额外商品")
    
    print(f"[PRINTER-ENHANCE] 处理完成，共 {len(enhanced_items)} 个商品")
    return enhanced_items


# 导入这些辅助函数
from .item_matcher import is_continuation_row, is_quantity_only_line, find_printer_item_match
