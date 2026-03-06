# requirement_fusion.py
def fuse_requirement(db_record: dict, attachment_text: str) -> str:
    """
    融合数据库字段 + 附件文本（互补策略）
    """
    project_name = db_record.get("project_name", "未知项目")
    lines = [f"项目名称: {project_name}"]
    
    # 1. 加入 DB 关键信息作为上下文提示
    names = db_record.get("commodity_names") or []
    if names:
        lines.append("采购商品参考: " + ", ".join(names))
    
    quantities = db_record.get("purchase_quantities") or []
    if quantities:
        lines.append("参考数量: " + ", ".join(quantities))
    
    brands = db_record.get("suggested_brands") or []
    if brands:
        lines.append("建议品牌参考: " + ", ".join(brands))
    
    # 2. 加入附件全文
    if attachment_text.strip():
        lines.append("\n【附件内容】\n" + attachment_text.strip())
    else:
        lines.append("\n【附件内容】\n（无有效附件）")
    
    return "\n".join(lines)
