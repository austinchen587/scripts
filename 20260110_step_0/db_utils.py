import psycopg2
import pandas as pd
from config import DB_CONFIG

def fetch_selected_procurements() -> pd.DataFrame:
    query = """
    SELECT
        pe.project_name,
        pe.project_number,
        pe.commodity_names,
        pe.parameter_requirements,
        pe.purchase_quantities,
        pe.suggested_brands,
        pe.related_links,
        pe.download_files,
        s.id AS supplier_id,
        s.name AS supplier_name,
        s.source AS supplier_source,
        sc.id AS commodity_id,
        sc.name AS commodity_name,
        sc.specification AS commodity_specification,
        sc.price AS commodity_price,
        sc.quantity AS commodity_quantity,
        sc.product_url AS commodity_product_url
    FROM procurement_purchasing pp
    JOIN procurement_emall pe ON pp.procurement_id = pe.id
    JOIN procurement_supplier_relation psr ON pp.id = psr.procurement_id
    JOIN procurement_suppliers s ON psr.supplier_id = s.id
    LEFT JOIN supplier_commodities sc ON s.id = sc.supplier_id
    WHERE pp.is_selected = true
    ORDER BY pe.project_number, s.id, sc.id;
    """
    with psycopg2.connect(**DB_CONFIG) as conn:
        df = pd.read_sql(query, conn)
    return df
