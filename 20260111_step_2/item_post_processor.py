# item_post_processor.py

def post_process_items(items, procurement_type):
    """
    对解析出的商品项进行后处理
    """
    processed_items = []
    
    for item in items:
        processed_item = {}
        
        # 标准化字段名称
        processed_item["商品名称"] = item.get("商品名称", "")
        processed_item["规格型号"] = item.get("规格型号", "")
        processed_item["建议品牌"] = item.get("建议品牌", item.get("品牌建议", ""))
        processed_item["采购数量"] = item.get("采购数量", "")
        processed_item["单位"] = item.get("单位", "")
        processed_item["备注"] = item.get("备注", "")
        
        # 清理空值和无效数据
        processed_item = {k: v for k, v in processed_item.items() if v and v not in ["-", "无", "None"]}
        
        # 如果商品名称不为空，添加到结果列表
        if processed_item.get("商品名称"):
            processed_items.append(processed_item)
    
    # 根据采购类型进行后续处理
    if procurement_type == "goods":
        processed_items = split_combined_items(processed_items)
    
    return processed_items

def split_combined_items(items):
    """拆分合并的商品项"""
    split_items = []
    
    for item in items:
        name = item.get("商品名称", "")
        specs = item.get("规格型号", "")
        
        # 检测是否包含多个商品
        if "；" in specs or "、" in name:
            # 尝试按分号拆分规格
            spec_parts = [part.strip() for part in specs.split("；") if part.strip()]
            if len(spec_parts) > 1:
                for i, spec in enumerate(spec_parts):
                    new_item = item.copy()
                    new_item["规格型号"] = spec
                    if i < len(spec_parts):
                        new_item["商品名称"] = f"{name}_{i+1}"
                    split_items.append(new_item)
            else:
                split_items.append(item)
        else:
            split_items.append(item)
    
    return split_items
