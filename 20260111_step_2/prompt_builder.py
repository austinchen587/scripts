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
    
    import json
    db_items_str = json.dumps(db_items, ensure_ascii=False, indent=2)

    prompt = f"""你是一位顶级的政企采购数据审计与融合专家。
现在，我将交给你两份核心数据：【系统数据库登记的初始采购项】和【实际采购附件中的明细文本】。
你的唯一任务是：综合分析这两份数据，进行“语义级智能融合”，最终输出【真正需要入库的商品清单】。

=== 1. 系统初始登记数据 (DB Items) ===
{db_items_str}

=== 2. 采购附件提取内容 (Attachment) ===
{attachment_text[:6000]} 

【🤖 智能融合与裁决法则（生死红线）】
请放弃任何死板的字面匹配，完全依靠你的商业常识和采购逻辑来决定最终有“几个”商品、分别“叫什么”：
1. **总包展开**：如果 DB 里只有 1 项（例如“办公家具一批”、“详见附件”），但附件里明确列出了具体的（办公桌、椅子、沙发）。你必须【舍弃总包概念，完全以附件明细为准】，直接输出多个具体的商品。
2. **跨服聊天合并（同物异名）**：如果 DB 叫“HUAWEI MateBook 14”，附件表格里叫“便携式计算机”。请你立刻凭借常识判断出这是【同一样东西的不同官方叫法】！请只输出 1 个商品，把附件的“Intel Core, OLED...”等参数全部完美地塞进这个商品的规格里。绝对不能因为名字不同就生出 2 条记录！
3. **按图索骥（参数补充）**：如果 DB 里已经登记了多个具体的商品，附件里刚好是这些商品的参数要求。请以 DB 商品为主体，从附件中精准抽取对应的尺寸、材质、售后要求，填入各自的 `规格型号` 字段中。
4. **互补防漏**：最终输出必须包含所有应该采购的实物。DB 里漏掉但附件里有明确数量/预算的，要加上；附件里没提但 DB 里明确登记的，要保留。
5. **参数合并铁律**：从附件提取的任何商品的多个参数（尺寸、材质、频段等），必须用分号(;)连成一段话，统一放在 `规格型号` 里。绝不允许给商品名称加 "_1"、"_2" 等奇葩后缀！
6. **电商平台偏好(search_platform)**：在推荐搜索平台时，【必须优先推荐“京东”或“淘宝”】。绝大多数办公、日用、数码、体育、家电等常规采购项，请固定填写“京东”或“淘宝”。除非是极其冷门的重工业原料，否则严禁推荐“1688”！

【输出格式要求】
请直接且仅输出一个 JSON 数组，数组中的每个对象代表一个最终入库的实体商品。
[
  {{
    "商品名称": "商品名（精简、准确）",
    "规格型号": "详细的技术参数与要求（多个参数用分号;隔开）",
    "建议品牌": "品牌（如有，否则填空）",
    "采购数量": "提取出的数字（如 155）",
    "单位": "个/台/批/支等",
    "备注": "预算、科室、商务售后要求等"
  }}
]

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