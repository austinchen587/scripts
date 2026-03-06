# output_formatter.py
import json
import re
import ast

def parse_llm_output(raw_output: str) -> list[dict]:
    """
    解析 LLM 输出的 JSON 数据 - 增强容错版
    支持：Markdown 清理、截断修复、正则强行提取、AST 评估
    """
    if not raw_output or not isinstance(raw_output, str):
        return []

    # 1. 基础清理：去掉 Markdown 代码块标识
    clean_output = raw_output.strip()
    if clean_output.startswith("```json"):
        clean_output = clean_output[7:]
    elif clean_output.startswith("```"):
        clean_output = clean_output[3:]
    
    if clean_output.endswith("```"):
        clean_output = clean_output[:-3]
    
    clean_output = clean_output.strip()

    # 2. 核心修复：处理截断的 JSON (处理因 Context 溢出导致的结尾缺失)
    # 如果发现有开括号但没闭括号，尝试人工补全
    if clean_output.startswith('[') and not clean_output.endswith(']'):
        # 统计大括号的平衡情况
        open_braces = clean_output.count('{')
        close_braces = clean_output.count('}')
        
        # 如果最后一个对象没写完（开大括号多于闭大括号），先把最后一个未完成的对象删掉，再闭合数组
        if open_braces > close_braces:
            last_brace_idx = clean_output.rfind('{')
            clean_output = clean_output[:last_brace_idx].strip()
            # 去掉末尾可能残留的逗号
            if clean_output.endswith(','):
                clean_output = clean_output[:-1].strip()
        
        # 强制闭合数组
        if not clean_output.endswith(']'):
            clean_output += ']'

    # 3. 尝试第一种解析方案：标准 json.loads
    try:
        data = json.loads(clean_output)
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            return data.get("items", [data])
    except Exception:
        pass

    # 4. 尝试第二种解析方案：正则强行提取所有 JSON 对象
    # 即使整个数组格式坏了，只要里面的 {"商品名称":...} 对象是完整的，就能提取出来
    try:
        items = []
        # 匹配大括号包围的商品对象
        matches = re.findall(r'\{[^{}]*(?:"商品名称"|"item_name")[^{}]*\}', clean_output)
        for m in matches:
            try:
                # 尝试修复对象内部可能的引号问题
                item = json.loads(m)
                if item:
                    items.append(item)
            except:
                # 尝试用 ast 评估单个对象
                try:
                    item = ast.literal_eval(m)
                    if isinstance(item, dict):
                        items.append(item)
                except:
                    continue
        if items:
            return items
    except Exception:
        pass

    # 5. 尝试第三种解析方案：ast.literal_eval (处理单引号等非标 JSON)
    try:
        # 尝试处理常见的单引号 JSON
        fixed_text = clean_output.replace("'", '"')
        fixed = ast.literal_eval(clean_output)
        if isinstance(fixed, list):
            return fixed
    except:
        pass

    # 6. 最后兜底：如果完全无法解析，返回错误信息
    print(f"[FORMATTER] ❌ 无法解析 LLM 输出。原始长度: {len(raw_output)}")
    return [{"error": "无法解析LLM输出", "raw": raw_output[:200]}]

def format_by_procurement_type(items, doc_type):
    """根据采购类型格式化输出"""
    if doc_type == "service":
        return _format_service_items(items)
    elif doc_type == "engineering":
        return _format_engineering_items(items)
    else:
        return _format_goods_items(items)

def _format_service_items(items):
    """服务类项目格式化"""
    formatted = []
    for item in items:
        service_item = {
            "服务名称": item.get("商品名称", "").replace("设施", "服务"),
            "服务内容": item.get("规格型号", ""),
            "服务期限": _extract_service_period(item),
            "服务地点": _extract_service_location(item),
            "服务标准": item.get("备注", "")
        }
        # 清理空值
        service_item = {k: v for k, v in service_item.items() if v}
        formatted.append(service_item)
    return formatted

def _extract_service_period(item):
    """从项目信息中提取服务期限"""
    text = f"{item.get('商品名称', '')} {item.get('规格型号', '')} {item.get('备注', '')}"
    
    # 匹配服务期限模式
    period_patterns = [
        r'服务期[限]?[:：]?\s*(\d+)\s*(年|月|天)',
        r'服务期限[:：]?\s*(\d+)\s*(年|月|天)',
        r'(\d+)\s*(年|月|天)\s*服务期',
        r'服务时间[:：]?\s*(\d+)\s*(年|月|天)'
    ]
    
    for pattern in period_patterns:
        match = re.search(pattern, text)
        if match:
            return f"{match.group(1)}{match.group(2)}"
    
    return "1年"  # 默认值

def _extract_service_location(item):
    """从项目信息中提取服务地点"""
    text = f"{item.get('商品名称', '')} {item.get('规格型号', '')} {item.get('备注', '')}"
    
    # 匹配地点模式
    location_patterns = [
        r'服务地点[:：]?\s*([^，。；\s]+)',
        r'地点[:：]?\s*([^，。；\s]+)',
        r'位于\s*([^，。；\s]+)',
        r'在\s*([^，。；\s]+)\s*(进行|开展|实施)'
    ]
    
    for pattern in location_patterns:
        match = re.search(pattern, text)
        if match:
            return match.group(1)
    
    return ""  # 无法提取时返回空

def _format_engineering_items(items):
    """工程类项目格式化"""
    formatted = []
    for item in items:
        engineering_item = {
            "工程名称": item.get("商品名称", ""),
            "工程内容": item.get("规格型号", ""),
            "工程规模": item.get("备注", ""),
            "工期": _extract_service_period(item),  # 复用服务期限提取
            "工程地点": _extract_service_location(item)  # 复用服务地点提取
        }
        # 清理空值
        engineering_item = {k: v for k, v in engineering_item.items() if v}
        formatted.append(engineering_item)
    return formatted

def _format_goods_items(items):
    """商品类项目格式化 - 增强版"""
    formatted = []
    for item in items:
        goods_item = {
            "商品名称": item.get("商品名称", ""),
            "规格型号": item.get("规格型号", ""),
            "建议品牌": item.get("建议品牌", item.get("品牌建议", "")),
            "采购数量": item.get("采购数量", ""),
            "单位": item.get("单位", ""),
            "备注": item.get("备注", "")
        }
        
        # 增强：如果规格型号包含品牌信息，提取到建议品牌
        specs = goods_item["规格型号"]
        if not goods_item["建议品牌"] and specs:
            # 常见打印机品牌
            brands = ["HP", "惠普", "佳能", "Canon", "兄弟", "Brother", 
                     "联想", "Lenovo", "爱普生", "Epson", "富士施乐", "Xerox",
                     "理光", "Ricoh", "京瓷", "Kyocera", "柯尼卡", "Konica",
                     "APeosport", "TOEC", "光电通"]
            for brand in brands:
                if brand in specs:
                    goods_item["建议品牌"] = brand
                    break
        
        # 清理空值
        goods_item = {k: v for k, v in goods_item.items() if v and str(v).strip()}
        formatted.append(goods_item)
    
    return formatted

def add_category_to_items(items: list[dict], category: str) -> list[dict]:
    """
    为商品项列表添加项目分类信息
    
    Args:
        items: 商品项列表
        category: 项目分类
        
    Returns:
        添加了分类信息的商品项列表
    """
    if not items:
        return items
    
    for item in items:
        # 为每个商品项添加项目分类信息
        item["所属项目分类"] = category
    
    return items

def format_with_category(items: list[dict], doc_type: str, project_category: str) -> list[dict]:
    """
    根据采购类型和项目分类格式化输出
    
    Args:
        items: 原始商品项列表
        doc_type: 采购类型（goods/service/engineering）
        project_category: 项目分类
        
    Returns:
        格式化后的商品项列表
    """
    # 先根据采购类型格式化
    formatted_items = format_by_procurement_type(items, doc_type)
    
    # 再添加项目分类信息
    categorized_items = add_category_to_items(formatted_items, project_category)
    
    return categorized_items
