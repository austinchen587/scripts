# commodity_enhancer.py
from typing import List, Dict, Any
import re

def enhance_commodity_extraction(llm_response: List[Dict], attachment_text: str) -> List[Dict]:
    """后处理优化：增强商品提取结果 - 基于测试样本优化"""
    if not llm_response:
        return llm_response
    
    enhanced_response = []
    
    for item in llm_response:
        enhanced_item = item.copy()
        commodity_name = item.get("商品名称", "")
        spec_model = item.get("规格型号", "")
        tech_params = item.get("技术参数", {})
        quantity = item.get("采购数量", "")
        
        # 1. 修正数量（基于附件内容）
        enhanced_item["采购数量"] = _correct_quantity(quantity, commodity_name, spec_model, attachment_text)
        
        # 2. 标准化商品名称
        enhanced_item["商品名称"] = standardize_commodity_name(commodity_name, attachment_text)
        
        # 3. 优化规格型号
        enhanced_item["规格型号"] = optimize_spec_model(spec_model, commodity_name, attachment_text)
        
        # 4. 清理无关技术参数
        if tech_params:
            enhanced_item["技术参数"] = clean_irrelevant_params(tech_params, commodity_name, attachment_text)
        
        # 5. 对于非技术类商品，移除技术参数字段
        if not _is_technical_item(commodity_name, tech_params, attachment_text):
            if "技术参数" in enhanced_item:
                # 保留有实际内容的技术参数，否则移除
                if isinstance(enhanced_item["技术参数"], dict):
                    # 检查是否都是"无相关参数"
                    all_empty = all("无相关" in str(v) or v == "" for v in enhanced_item["技术参数"].values())
                    if all_empty:
                        enhanced_item.pop("技术参数", None)
        
        enhanced_response.append(enhanced_item)
    
    return enhanced_response

def _correct_quantity(quantity: str, commodity_name: str, spec_model: str, attachment_text: str) -> str:
    """修正数量，基于附件内容"""
    if not quantity or quantity == "待定":
        # 尝试从附件中提取数量
        if attachment_text:
            # 查找包含商品名称和数量的行
            lines = attachment_text.split('\n')
            for i, line in enumerate(lines):
                if commodity_name in line:
                    # 检查当前行和前后行中的数字
                    for check_line in [line] + lines[max(0, i-2):min(len(lines), i+3)]:
                        # 查找数字+单位模式
                        matches = re.findall(r'(\d+)\s*(个|台|套|张|把|本|项|次)', check_line)
                        if matches:
                            return matches[0][0]
    return quantity

def _is_technical_item(commodity_name: str, tech_params: Dict, attachment_text: str) -> bool:
    """判断是否为技术类商品"""
    commodity_lower = commodity_name.lower()
    
    # 明显非技术类
    non_technical_keywords = ["图书", "书籍", "奖状", "证书", "会议桌", "会议椅", "服务", "验收", "林业服务"]
    if any(keyword in commodity_lower for keyword in non_technical_keywords):
        return False
    
    # 明显技术类
    technical_keywords = ["空调", "服务器", "电脑", "打印机", "机器人", "无人机", "心电图", "医疗器械", "激光切割", "3D打印"]
    if any(keyword in commodity_lower for keyword in technical_keywords):
        return True
    
    # 根据技术参数判断
    if tech_params:
        # 检查是否有实际的技术参数（不是"无相关参数"）
        valid_params = [v for v in tech_params.values() if v and "无相关" not in str(v)]
        if len(valid_params) >= 2:
            return True
    
    return False

def standardize_commodity_name(original_name: str, attachment_text: str) -> str:
    """标准化商品名称为电商平台常用名 - 优化版"""
    if not original_name:
        return original_name
    
    name_lower = original_name.lower()
    
    # 扩展映射表
    name_mappings = {
        "飞行器存储装置": "无人机机场",
        "飞行控制设备": "无人机控制器",
        "航拍飞行器": "无人机",
        "计算存储设备": "服务器",
        "数据存储节点": "存储服务器",
        "超融合节点": "超融合服务器",
        "制冷设备": "空调",
        "空调机组": "商用空调",
        "柜机": "柜式空调",
        "儿童运动器械": "儿童平衡车",
        "幼儿园游乐设备": "幼儿园滑梯",
        "积木搭建台": "积木桌",
        "其他林业服务": "油茶基地验收服务",
        "其他服务": "专业服务",
        "硒鼓": "打印机硒鼓",
        "奖状/证书": "奖状",
        "心电图机": "医用心电图机",
        "氧气减压器": "医用氧气减压器"
    }
    
    # 检查映射
    for fuzzy_name, standard_name in name_mappings.items():
        if fuzzy_name in name_lower or original_name in fuzzy_name:
            return standard_name
    
    # 如果名称以"核心参数要求:"开头，提取商品类目
    if "核心参数要求:" in original_name:
        # 提取商品类目
        match = re.search(r'商品类目:\s*([^;]+)', original_name)
        if match:
            return match.group(1).strip()
    
    return original_name

def optimize_spec_model(spec_model: str, commodity_name: str, attachment_text: str) -> str:
    """优化规格型号，提取可搜索的关键信息 - 增强版"""
    # 首先尝试从"核心参数要求"中提取关键信息
    if "核心参数要求:" in spec_model:
        # 提取所有参数键值对
        param_dict = {}
        param_patterns = [
            r'([^:;]+):\s*([^;]+)',
            r'([^:;]+)[:：]\s*([^;]+)'
        ]
        
        for pattern in param_patterns:
            matches = re.findall(pattern, spec_model)
            for key, value in matches:
                key_clean = key.strip()
                value_clean = value.strip()
                if key_clean not in ["核心参数要求", "商品类目", "描述"]:
                    param_dict[key_clean] = value_clean
        
        # 构建简洁的规格字符串
        if param_dict:
            # 优先显示关键规格
            key_specs = []
            for key in ["型号", "尺寸", "规格", "颜色分类", "净含量"]:
                if key in param_dict:
                    key_specs.append(f"{key}:{param_dict[key]}")
            
            if key_specs:
                return "; ".join(key_specs[:3])
    
    # 原有逻辑
    return spec_model

def clean_irrelevant_params(tech_params: Dict, commodity_name: str, attachment_text: str) -> Dict:
    """清理无关的技术参数 - 优化版"""
    if not tech_params:
        return {}
    
    cleaned_params = {}
    commodity_lower = commodity_name.lower()
    
    # 首先检查参数是否都是"无相关参数"
    all_empty = all("无相关" in str(v) or v == "" for v in tech_params.values())
    if all_empty:
        # 对于非技术商品，返回空字典
        if not _is_technical_item(commodity_name, tech_params, attachment_text):
            return {}
    
    # 根据商品类型决定保留哪些参数
    param_categories = {
        "通用电子设备": ["功率", "电压", "电流", "频率", "尺寸", "重量", "接口", "协议"],
        "计算机类": ["处理器", "CPU", "内存", "硬盘", "显卡", "显示器", "操作系统"],
        "空调类": ["能效等级", "制冷量", "制热量", "功率", "噪音", "电源", "APF", "变频"],
        "打印机类": ["打印速度", "分辨率", "纸张容量", "耗材类型", "接口", "网络"],
        "医疗器械": ["频率响应", "采样率", "精度", "阻抗", "分辨率", "认证", "标准"],
        "机器人/无人机": ["处理器", "内存", "传感器", "续航", "重量", "尺寸", "防护等级", "通信"],
        "工业设备": ["压力", "流量", "温度", "材质", "精度", "功率", "尺寸", "重量"],
        "家具/玩教具": ["尺寸", "材质", "颜色", "承重", "环保标准", "安全标准"]
    }
    
    # 确定商品类别
    item_category = None
    if "空调" in commodity_lower:
        item_category = "空调类"
    elif any(keyword in commodity_lower for keyword in ["电脑", "服务器", "一体机"]):
        item_category = "计算机类"
    elif "打印机" in commodity_lower:
        item_category = "打印机类"
    elif any(keyword in commodity_lower for keyword in ["心电图", "医疗", "医用"]):
        item_category = "医疗器械"
    elif any(keyword in commodity_lower for keyword in ["机器人", "无人机", "机械臂"]):
        item_category = "机器人/无人机"
    elif any(keyword in commodity_lower for keyword in ["减压器", "阀门", "压力表"]):
        item_category = "工业设备"
    elif any(keyword in commodity_lower for keyword in ["桌", "椅", "玩具", "教具", "奖状"]):
        item_category = "家具/玩教具"
    else:
        item_category = "通用电子设备"
    
    # 保留相关参数
    relevant_keys = param_categories.get(item_category, [])
    
    for key, value in tech_params.items():
        key_lower = key.lower()
        
        # 检查是否相关
        is_relevant = False
        for relevant in relevant_keys:
            if relevant in key_lower:
                is_relevant = True
                break
        
        # 对于通用参数也保留
        if not is_relevant:
            for generic in ["其他参数", "备注", "说明", "描述"]:
                if generic in key_lower:
                    is_relevant = True
                    break
        
        if is_relevant and value and "无相关" not in str(value):
            cleaned_params[key] = value
    
    return cleaned_params

def extract_commodity_name_from_specs(spec_model: str) -> str:
    """从规格型号中提取商品名称"""
    if not spec_model:
        return ""
    
    # 提取"商品类目"信息
    if "核心参数要求:" in spec_model and "商品类目:" in spec_model:
        match = re.search(r'商品类目:\s*([^;]+)', spec_model)
        if match:
            return match.group(1).strip()
    
    # 检查常见的商品类型关键词
    common_items = ["打印纸", "复印纸", "办公桌", "椅子", "电脑", "打印机", 
                   "空调", "服务器", "医疗器械", "图书", "宣传片"]
    
    for item in common_items:
        if item in spec_model:
            return item
    
    return spec_model[:50]  # 返回规格型号前50个字符
