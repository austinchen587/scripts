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
    
    # 【修复】：由于我们在大模型Prompt中已经严格要求合并参数，
    # 绝对不能再按分号(;)进行拆分，直接返回大模型吐出的原始对象数组！
    return processed_items

# 删除了原来那个坑爹的 split_combined_items 函数


