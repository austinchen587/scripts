# prompt_builder.py
from typing import List, Dict
from prompt_components import build_db_summary, build_technical_procurement_prompt, build_general_procurement_prompt
from content_analyzer import detect_technical_content, preprocess_attachment_text, analyze_item_type
from commodity_enhancer import enhance_commodity_extraction
import re

def build_enhanced_prompt(db_items: List[Dict], attachment_text: str, 
                         similar_cases: List[Dict], doc_type: str) -> str:
    """构建增强版提示词 - 基于测试样本优化"""
    
    # 基础DB信息总结
    db_summary = build_db_summary(db_items)
    
    # 分析文档特征，判断是否需要技术模式
    is_technical_procurement = detect_technical_content(attachment_text)
    
    prompt = f"""你是一位专业的政府采购专家。请基于数据库信息和附件内容，生成完整的采购需求清单。

【核心优化要求】
1. 数量准确性：必须从表格或清单中提取准确数量，不要自行推测
2. 参数相关性：技术参数必须与商品类型匹配，不要填充无关参数
3. 规格完整性：提取完整的规格型号，避免"长*宽*高"这样不完整的信息
4. 商品名称：使用具体明确的名称，避免"其他服务"等模糊名称
5. DB信息作为参考，附件信息优先级更高
6. 绝对忠实原文(反幻觉)：只允许提取【附件内容】中实际出现的商品，【历史参考案例】仅供格式和专业术语参考。绝对禁止将历史案例中的无关商品（如防疫物资等）添加到本次清单中！如果你在附件中找不到内容，宁可返回空数据，也严禁无中生有！
7. 严禁偷懒省略(完整性警告)：必须逐行完整提取原表中的【所有】商品（哪怕有100行也必须全部写出）。绝不允许在中途跳过任何商品，绝不允许使用“等”、“...”或省略号！必须老老实实把最后一行前的所有项目全部列出！
8. 严禁过度拆分(强制合并参数)：如果原表中同一个商品（如“中长跑测试仪”）跨越多行包含不同的技术参数，【必须】将它们全部合并到同一个商品的“规格型号”或“备注”字段中！绝对不允许给商品名称添加“_1”、“_2”等后缀！绝对不允许把同一个商品拆分成多个独立的项目！
9. 电商平台偏好(search_platform)：在推荐搜索平台时，【必须优先推荐“京东”或“淘宝”】。绝大多数办公、日用、数码、体育、家电等常规采购项，请固定填写“京东”或“淘宝”。除非是极其冷门的重工业原料，否则严禁推荐“1688”！
10. 【非表格/海报类文档提取强制规则】：当附件内容为碎片化文本（如图文海报OCR提取的散落文本）时，你必须上下连贯阅读！如果“商品名”的上下文中出现了数字、尺寸（如55W、16寸、178mm）、型号（如KG316T）或材质说明，即使它们没有标明“规格”二字，你也【必须】主动将这些散落的属性收集起来，全部填入该商品的“规格型号”字段中！绝对不允许遗漏！
11. 严防表格列错位(空列处理)：在提取包含逗号或制表符分隔的表格文本时，必须严格对齐表头列数！如果某商品的“规格/技术参数”列在原文中为空（例如看到连续的逗号 `,,`），则必须将其“规格型号”字段置为空字符串 `""`。绝对禁止跨列提取，严禁把排在后面的“单价”、“数量”或“总价”（如 0.8、13、200）错误当成规格填入！
12. 【规格防幻觉铁律】：“规格型号”必须是具体的材质、尺寸、物理参数或官方商品代码。绝对禁止将“施工地点”、“学校名称”、“项目地址”或“人名”（如“XX学校校园内”）当成规格型号填入！如果在原文中确实找不到具体的参数规格，请直接将其置为空字符串 `""` 或者填 `"无"`，宁可留空也绝不能生搬硬套！


【表格数据处理】
如果附件中有表格数据（包含序号、名称、数量、单位等列）：
- 严格按照表格逐行提取每个商品项
- 表格中的"数量"列必须准确提取
- 表格中的"规格型号"或"参数"列尽量完整提取

【非表格/碎片化图文数据处理】
如果附件内容是零散的（如OCR从图片、宣传手册中提取的文本）：
- 必须根据上下文语境，将商品名称与其附近出现的尺寸、功率、型号、材质等关键参数进行绑定合并。
- 绝不能因为排版散乱就只提取商品名而让“规格型号”为空！如果原文图片中有参数，必须提取出来。

【附件内容特征】
{_analyze_attachment_features(attachment_text)}

【数据库参考信息】
{db_summary}

【附件内容】（重点关注技术参数和表格数据）
{preprocess_attachment_text(attachment_text)}

【历史参考案例】
"""
    
    # 找到添加相似案例的地方，修改为：
    valid_cases = [c for c in similar_cases if c.get('content')]
    # 核心修复：如果附件文本已经很长了（比如超过3000字），就不要再塞案例了，把空间留给输出
    if valid_cases and len(attachment_text) < 3000: 
        for i, case in enumerate(valid_cases, 1):
            # ... 原有的添加案例代码 ...
            pass
    else:
        prompt += "\n（因附件内容较多，已省略历史参考案例以确保生成完整）\n"
    
    # 根据采购类型和内容特征提供具体要求
    if is_technical_procurement:
        prompt += build_technical_procurement_prompt(doc_type, attachment_text)
    else:
        prompt += build_general_procurement_prompt(doc_type)
    
    prompt += """
【关键注意事项】
1. 数量问题：仔细核对附件中的数量，不要将"1批"误解为多个
2. 服务类项目：服务类不需要技术参数字段
3. 图书类项目：规格型号使用ISBN号，备注包含出版社和定价
4. 模糊名称处理："其他服务"等模糊名称要具体化
5. 参数填充：不要为所有商品都添加相同的技术参数模板
6. 强制合并合并！同一个商品的多个参数绝对不能拆分成多个商品对象！
7. 平台导向：search_platform 字段请填写“京东”或“淘宝”。

请严格按照以上要求和格式生成JSON数组："""
    
    return prompt

def _analyze_attachment_features(attachment_text: str) -> str:
    """分析附件特征，提供提取指导"""
    if not attachment_text:
        return "无附件内容"
    
    features = []
    
    # 检查是否有表格 - 修正后的正则表达式
    # 匹配：数字 + 空格 + 任意非换行字符 + 空格 + 数字 + 空格 + 单位
    if re.search(r'\d+\s+[^\n]+\s+\d+\s+[个台套张把本项]', attachment_text):
        features.append("附件包含表格数据，请逐行提取")
    
    # 检查是否有详细技术参数 - 修正后的正则表达式
    if re.search(r'技术参数|技术要求|规格型号|配置要求', attachment_text):
        features.append("附件包含详细技术参数，请仔细提取")
    
    # 检查是否有商务要求 - 修正后的正则表达式
    if re.search(r'商务要求|交付期限|质保期|售后服务', attachment_text):
        features.append("附件包含商务要求，请提取到商务要求字段")
    
    # 检查是否有预算信息 - 修正后的正则表达式
    if re.search(r'预算[金额]*[:：]\s*\d+', attachment_text) or re.search(r'\d+\s*元', attachment_text):
        features.append("附件包含预算信息，请提取到预算信息字段")
    
    if features:
        return "附件特征分析：\n- " + "\n- ".join(features)
    else:
        return "附件为一般性描述文档，请仔细阅读提取关键信息"

def build_table_aware_prompt(db_items: List[Dict], attachment_text: str, 
                            similar_cases: List[Dict], doc_type: str) -> str:
    """
    专门针对表格数据的提示词 - 强化规格提取与搜索导向
    """
    base_prompt = build_enhanced_prompt(db_items, attachment_text, similar_cases, doc_type)
    
    # 插入Markdown表格处理指令
    table_instructions = """
    
【⭐⭐ 核心任务：电商搜索级参数提取 ⭐⭐】
请注意：你提取的数据将直接用于**电商平台搜索比价**。
1. **规格/型号是灵魂**：如果没有具体的规格型号（如 CPU型号、打印机型号、空调匹数、纸张克重），我们无法找到对应商品。
   - 错误示例：{"商品名称": "电脑", "规格型号": "台式机"} -> 无法搜索
   - 正确示例：{"商品名称": "台式电脑", "规格型号": "i7-12700/16G/512G/27寸显示器"} -> 准确搜索

2. **表格结构分析（思维链）**：
   - 第一步：先看表格的表头（Markdown格式），确定哪一列是"名称"，哪一列是"参数/型号/规格"。
   - 第二步：往往"名称"列很简单（如"打印机"），而"参数"列很长。请将长文本完整提取到"规格型号"字段。
   - 第三步：如果"备注"列包含"含安装"、"原装"等关键信息，也请提取。

3. **数据提取要求**：
   - **不丢失关键参数**：不要为了简化而删除原文中的型号代码（如 "M4300"、"K3"）。
   - **拆分合并行**：如果一行中有多个商品（如"电脑及打印机"），请拆分为两个对象。
   - **保持原文**：对于复杂的参数，直接复制原文，不要自己总结摘要。

"""
    
    # 将表格指令插入到【附件内容】之前，确保高优先级
    prompt_parts = base_prompt.split("【附件内容】")
    if len(prompt_parts) > 1:
        # 在附件内容前插入指令
        return prompt_parts[0] + table_instructions + "\n【附件内容】" + prompt_parts[1]
    else:
        return base_prompt + table_instructions
    
    
def _detect_procurement_table(text: str) -> bool:
    """检测是否为采购表格"""
    if not text:
        return False
    
    # 表格特征检测
    table_features = [
        # 标题行特征
        r'序号\s+[物资商品]名称',
        r'物资名称\s+规格型号',
        r'规格型号\s+主要技术参数',
        r'预算单价.*预算合计',
        # 数据行特征（有规律的列）
        r'\d+\s+[^\n]{10,}\s+[^\n]{10,}\s+\d+\s*[张套个把本项]',
        # 典型的表格结构
        r'^\s*\d+\s+[^\n]+(?:\s+\d+)+\s*$',
    ]
    
    lines = text.split('\n')
    table_lines_count = 0
    
    for line in lines:
        line_stripped = line.strip()
        if not line_stripped:
            continue
            
        # 检查是否可能是表格数据行
        is_possible_table_row = False
        
        # 有序列号开头
        if re.match(r'^\d+[\.、]?\s+', line_stripped):
            is_possible_table_row = True
        
        # 包含典型表格字符
        if re.search(r'\d+\s*[张套个把本项]\s+\d+', line_stripped):
            is_possible_table_row = True
        
        if is_possible_table_row:
            table_lines_count += 1
    
    # 如果有连续的多行表格数据，认为是表格
    return table_lines_count >= 3