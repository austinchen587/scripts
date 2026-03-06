# procurement_classifier.py
import re

def classify_procurement_type(project_name, attachment_text, db_record):
    """增强的采购类型分类器，识别技术类采购"""
    text_for_analysis = f"{project_name} {attachment_text}".lower()
    
    # 首先检查是否为技术类采购
    if _is_technical_procurement(attachment_text):
        return "technical_goods"  # 特殊的技术货物类
    
    # 货物类关键词
    goods_keywords = [
        '打印机', '碳粉', '感光鼓', '耗材', '墨盒', '硒鼓',
        '设备', '仪器', '电脑', '服务器', '计算机', '办公用品',
        '教学设备', '实验仪器', '医疗设备', '体育器材', '空调',
        '家具', '器材', '物资'
    ]
    
    # 服务类关键词
    service_keywords = [
        '运维', '服务', '维护', '保养', '管理', '托管', '监理',
        '咨询', '设计', '检测', '监测', '保洁', '保安', '培训'
    ]
    
    # 工程类关键词  
    engineering_keywords = [
        '工程', '施工', '安装', '建设', '改造', '装修', '修缮',
        '土建', '钢结构', '防水', '装饰'
    ]
    
    goods_count = sum(1 for word in goods_keywords if word in text_for_analysis)
    service_count = sum(1 for word in service_keywords if word in text_for_analysis)
    engineering_count = sum(1 for word in engineering_keywords if word in text_for_analysis)
    
    if goods_count >= max(service_count, engineering_count):
        return "goods"
    elif service_count >= max(goods_count, engineering_count):
        return "service"
    elif engineering_count >= max(goods_count, service_count):
        return "engineering"
    else:
        return "goods"  # 默认货物类

def _is_technical_procurement(attachment_text: str) -> bool:
    """判断是否为技术类采购文档"""
    if not attachment_text:
        return False
    
    technical_indicators = [
        r'技术参数', r'技术要求', r'性能指标', r'★', r'核心参数',
        r'能效', r'功率', r'制冷量', r'制热量', r'噪音', r'dB\(A\)',
        r'APF', r'W\)', r'Hz', r'电压', r'电流', r'频率',
        r'商务要求', r'交付期限', r'质保期', r'售后服务', r'验收标准'
    ]
    
    text_lower = attachment_text.lower()
    technical_matches = sum(1 for indicator in technical_indicators 
                           if re.search(indicator, text_lower))
    
    # 同时检查是否有具体的数值参数模式
    numeric_patterns = [
        r'≥?\d+\.?\d*\s*(W|dB|Hz|V|A)',
        r'\d+\s*台?[内后]',
        r'质保.*\d+.*年'
    ]
    
    numeric_matches = sum(1 for pattern in numeric_patterns 
                         if re.search(pattern, text_lower))
    
    return technical_matches >= 3 or numeric_matches >= 2

def classify_service_subtype(project_name: str, attachment_text: str) -> str:
    """识别服务子类型"""
    text = f"{project_name} {attachment_text}".lower()
    
    if any(keyword in text for keyword in ["宣传片", "拍摄", "视频制作"]):
        return "媒体制作服务"
    elif any(keyword in text for keyword in ["消防", "救援", "驻勤"]):
        return "消防物资服务"
    elif any(keyword in text for keyword in ["验收", "检测", "监理"]):
        return "专业检测服务"
    elif any(keyword in text for keyword in ["维修", "保养", "维护"]):
        return "设备维护服务"
    elif any(keyword in text for keyword in ["培训", "教育", "教学"]):
        return "教育培训服务"
    else:
        return "其他专业服务"
