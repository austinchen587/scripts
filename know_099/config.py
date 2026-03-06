# D:\code\project\scripts\know_099\config.py

# 数据库配置
DB_CONFIG = {
    "dbname": "austinchen587_db",
    "user": "austinchen587",
    "password": "austinchen587",
    "host": "localhost",
    "port": 5432
}

# 表名定义
TABLE_SOURCE = "procurement_commodity_sku_know"      # 源数据表 (只读)
TABLE_RESULT = "procurement_commodity_sku_know_result" # 结果记录表
TABLE_NODES = "kg_nodes"                             # 图谱点表
TABLE_EDGES = "kg_edges"                             # 图谱边表

# Ollama配置
OLLAMA_MODEL = "qwen2.5:7b-instruct-q4_K_M"
OLLAMA_URL = "http://localhost:11434/api/chat"

# 提示词模板 (深度优化版)
# 针对痛点：品牌乱填、规格嵌套、无效值
PROMPT_TEMPLATE = """
你是一个资深采购数据清洗专家。请从杂乱的电商标题中精准提取结构化属性。

【提取规则 - 必须严格遵守】
1. 品牌 (Brand)：
   - 必须是具体的品牌名词（如“联想”、“得力”）。
   - ❌ **严禁**将以下词汇视为品牌：新款、潮牌、外贸、正品、清仓、推荐、品牌、未知、无、/、男装、女装。
   - 如果标题未提及品牌，请直接返回空字符串 ""。
2. 规格 (Spec)：
   - 提取尺寸、重量、容量、包装规格、厚度等。
   - ❌ **严禁**输出嵌套的JSON对象（如 {{"尺寸":...}}），必须合并为一个字符串（用逗号分隔）。
   - 示例："100ml, 2瓶装"
3. 材质 (Material)：提取面料、填充物、材质成分。
4. 适用对象 (Target)：提取性别、人群。
5. 颜色 (Color)：提取具体的颜色名称。

商品标题：{title}

【输出要求】
只输出一个标准的 JSON 对象，所有字段值必须是字符串(String)。不要包含Markdown标记。

JSON示例：
{{
    "品牌": "七匹狼",
    "型号": "1002",
    "材质": "纯棉, 聚酯纤维",
    "规格": "XL, 加厚, 冬季款",
    "颜色": "黑色",
    "适用对象": "男士"
}}
"""