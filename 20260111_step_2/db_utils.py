import psycopg2
import pandas as pd
import numpy as np
from config import DB_CONFIG

def _parse_array_field(val):
    """安全解析 PostgreSQL 数组字段"""
    if val is None: return []
    if isinstance(val, (list, tuple)): return [str(x).strip() for x in val if x is not None and str(x).strip() != '']
    if isinstance(val, np.ndarray): return [str(x).strip() for x in val if x is not None and str(x).strip() != '']
    if pd.isna(val): return []
    
    if isinstance(val, str):
        clean = val.strip()
        if not clean or clean == "{}": return []
        if clean.startswith('{') and clean.endswith('}'): clean = clean[1:-1]
        parts = []
        for part in clean.split(','):
            p = part.strip().strip('"').strip("'")
            if p: parts.append(p)
        return parts
    try:
        s = str(val).strip()
        return [s] if s else []
    except: return []

def fetch_goods_procurements(limit=None, offset=0):
    """
    获取所有 goods 类型的采购主数据
    【关键修改】直接在SQL中排除已处理记录，配合LIMIT使用
    """
    query = """
    SELECT 
        pe.id AS procurement_id,
        pe.project_name,
        pe.project_number,
        pe.commodity_names,
        pe.parameter_requirements,
        pe.purchase_quantities,
        pe.control_amounts,
        pe.suggested_brands,
        pe.business_items,
        pe.business_requirements,
        pe.related_links,
        pe.download_files
    FROM procurement_emall_category pec
    JOIN procurement_emall pe ON pec.record_id = pe.id
    WHERE pec.category = 'goods'
    -- 👇 暂时注释掉这行：允许抓取所有项目，包括已过期的
    -- AND pe.quote_end_time::TIMESTAMP > CURRENT_TIMESTAMP
    
    -- 【核心优化】直接排除已经存在于结果表中的记录
    -- 这样每次 LIMIT 10 拿到的永远是"真正待处理"的最新 10 条
    AND pe.id NOT IN (
        SELECT procurement_id FROM procurement_commodity_category
    )
    
    ORDER BY pe.id DESC
    """
    
    # 加上限制
    if limit is not None:
        query += f" LIMIT {limit} OFFSET {offset}"
    
    with psycopg2.connect(**DB_CONFIG) as conn:
        df = pd.read_sql(query, conn)

    array_fields = [
        "commodity_names", "parameter_requirements", "purchase_quantities",
        "control_amounts", "suggested_brands", "business_items",
        "business_requirements", "related_links", "download_files"
    ]

    for field in array_fields:
        if field in df.columns:
            df[field] = df[field].apply(_parse_array_field)

    return df

def fetch_total_count():
    """获取goods类型且未过期的 待处理 记录总数"""
    query = """
    SELECT COUNT(*) as total
    FROM procurement_emall_category pec
    JOIN procurement_emall pe ON pec.record_id = pe.id
    WHERE pec.category = 'goods'
      -- AND pe.quote_end_time::TIMESTAMP > CURRENT_TIMESTAMP
      -- 统计时也排除已处理的
      AND pe.id NOT IN (
          SELECT procurement_id FROM procurement_commodity_category
      )
    """
    
    with psycopg2.connect(**DB_CONFIG) as conn:
        cursor = conn.cursor()
        cursor.execute(query)
        result = cursor.fetchone()
        return result[0] if result else 0

def fetch_processed_records():
    """保留接口兼容性"""
    return []