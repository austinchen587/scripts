# content_analyzer.py
import re
from typing import Dict, List, Set

def detect_technical_content(attachment_text: str) -> bool:
    """检测是否为技术类采购文档 - 优化版"""
    if not attachment_text:
        return False
    
    # 分类型检测，避免通用办公设备被误判为技术类
    technical_indicators = [
        # 强技术指标
        r'能效[等级]*', r'功率', r'制冷量', r'制热量', r'噪音.*dB', 
        r'技术参数', r'技术要求', r'性能指标', r'APF', r'Hz',
        # 医疗设备指标
        r'频率响应', r'采样率', r'输入阻抗', r'定标电压',
        # 机器人/电子设备指标
        r'主控芯片', r'处理器', r'内存', r'存储',
        # 商务要求
        r'商务要求', r'交付期限', r'质保期', r'售后服务'
    ]
    
    text_lower = attachment_text.lower()
    
    # 排除通用办公设备的关键词
    general_office_keywords = ['会议桌', '会议椅', '奖状', '证书', '硒鼓', '碳粉', '图书', '书籍']
    
    # 如果包含大量通用办公设备关键词，降低技术权重
    office_count = sum(1 for keyword in general_office_keywords if keyword in attachment_text)
    if office_count >= 3:
        # 需要更多技术指标才认为是技术类
        technical_count = sum(1 for indicator in technical_indicators 
                             if re.search(indicator, text_lower))
        return technical_count >= 5
    else:
        technical_count = sum(1 for indicator in technical_indicators 
                             if re.search(indicator, text_lower))
        return technical_count >= 3

def analyze_item_type(attachment_text: str) -> str:
    """分析附件内容，确定主要商品类型 - 优化版"""
    if not attachment_text:
        return ""
    
    text_lower = attachment_text.lower()
    
    # 更精确的类型检测，使用权重系统
    type_scores = {}
    
    # 类型关键词及其权重
    type_patterns = {
        "无人机": {
            "keywords": ["无人机", "飞行器", "航拍", "巡检无人机", "飞行控制器"],
            "weight": 2
        },
        "服务器": {
            "keywords": ["服务器", "机架", "存储", "计算节点", "超融合", "i5-", "i7-"],
            "weight": 2
        },
        "空调": {
            "keywords": ["空调", "制冷", "制热", "匹柜机", "能效等级", "APF", "变频", "柜式空调"],
            "weight": 3  # 空调关键词权重更高，因为技术参数固定
        },
        "玩教具": {
            "keywords": ["玩具", "教具", "幼儿园", "儿童", "滑梯", "平衡车", "奖状"],
            "weight": 2
        },
        "办公设备": {
            "keywords": ["电脑", "打印机", "投影仪", "复印机", "一体机", "台式电脑"],
            "weight": 2
        },
        "图书": {
            "keywords": ["图书", "书籍", "ISBN", "出版社", "定价", "书目"],
            "weight": 3  # 图书关键词权重更高
        },
        "医疗器械": {
            "keywords": ["心电图", "医疗器械", "医疗设备", "医用", "心率", "血压"],
            "weight": 2
        },
        "工业设备": {
            "keywords": ["减压器", "压力", "MPa", "流量", "工业设备", "阀门"],
            "weight": 2
        }
    }
    
    # 计算各类型得分
    for item_type, pattern in type_patterns.items():
        score = 0
        for keyword in pattern["keywords"]:
            if keyword in text_lower:
                score += pattern["weight"]
        if score > 0:
            type_scores[item_type] = score
    
    if not type_scores:
        return ""
    
    # 获取得分最高的类型
    main_type = max(type_scores.items(), key=lambda x: x[1])[0]
    
    # 构建类型提示
    hint = f"\n【检测到的商品类型：{main_type}】\n"
    
    if main_type == "无人机":
        hint += "技术参数应包含：重量、尺寸、防护等级、电源要求、续航时间。\n"
        hint += "不要包含空调参数（能效等级、制冷量、制热量等）。\n"
    elif main_type == "服务器":
        hint += "技术参数应包含：处理器型号、内存、硬盘、尺寸(U数)、电源功率、接口类型。\n"
        hint += "不要包含空调参数。\n"
    elif main_type == "空调":
        hint += "技术参数应包含：能效等级、制冷制热量、功率、噪音、电源要求。\n"
        hint += "可以包含所有空调相关参数。\n"
    elif main_type == "玩教具":
        hint += "技术参数应包含：尺寸、材质、承重、安全标准、适用年龄。\n"
        hint += "不要包含电子设备参数（功率、能效等）。\n"
    elif main_type == "办公设备":
        hint += "技术参数应包含：处理器、内存、硬盘、接口、操作系统。\n"
        hint += "对于打印机：打印速度、分辨率、纸张容量。\n"
    elif main_type == "图书":
        hint += "规格型号使用ISBN号，不需要技术参数字段。\n"
        hint += "商务要求：交货时间、图书质量、配送要求。\n"
    elif main_type == "医疗器械":
        hint += "技术参数应包含：医疗专用参数（频率响应、采样率、精度等）。\n"
        hint += "需要医疗器械相关认证信息。\n"
    elif main_type == "工业设备":
        hint += "技术参数应包含：压力范围、流量、材质、精度、工作温度。\n"
    
    return hint

def preprocess_attachment_text(attachment_text: str) -> str:
    """预处理附件文本，突出重要信息 - 优化版"""
    if not attachment_text:
        return "无附件信息"
    
    # 限制长度但保留技术参数部分
    if len(attachment_text) > 4000:
        # 尝试保留包含技术参数的部分
        lines = attachment_text.split('\n')
        technical_lines = []
        general_lines = []
        table_lines = []
        
        for line in lines:
            # 检测表格行（包含制表符或连续的数字/单位）
            if re.search(r'\t|(\d+[\.\d]*\s*[\u4e00-\u9fa5a-zA-Z]{1,2})|(\d+(mm|kg|W|Hz|cm|L|ml|g|克))', line):
                table_lines.append(line)
            elif any(keyword in line for keyword in ['★', '技术', '参数', '要求', 'dB', 'W)', 'Hz', '型号', '规格', '配置', '处理器', '内存', '硬盘']):
                technical_lines.append(line)
            else:
                general_lines.append(line)
        
        # 优先保留表格和技术参数行
        preserved_text = ""
        
        if table_lines:
            # 把限制放宽到 500 行，让 100 多项的超长表格也能完整传给大模型
            preserved_text += "\n【表格数据】\n" + '\n'.join(table_lines[:500]) + "\n"
        
        if technical_lines:
            technical_text = '\n'.join(technical_lines)
            if len(technical_text) > 2000:
                preserved_text += "\n【技术参数（截断）】\n" + technical_text[:2000] + "...\n"
            else:
                preserved_text += "\n【技术参数】\n" + technical_text + "\n"
        
        # 添加部分通用内容
        if preserved_text:
            preserved_text += "\n【其他内容】\n" + '\n'.join(general_lines[:20])
        else:
            preserved_text = '\n'.join(lines[:100])
        
        return preserved_text[:3500] + ("..." if len(attachment_text) > 3500 else "")
    
    return attachment_text[:3000] + ("..." if len(attachment_text) > 3000 else "")
