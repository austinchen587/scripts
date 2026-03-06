
# D:\code\project\scripts\20251227\build_brand_keyword_map.py
import os
import json
import psycopg2
import pandas as pd
from pathlib import Path
from collections import defaultdict
from dotenv import load_dotenv

load_dotenv()

OUTPUT_DIR = Path(r"D:\code\project\scripts\20251227")
DB_CONFIG = {
    "host": "localhost",
    "port": 5432,
    "database": "austinchen587_db",
    "user": "austinchen587",
    "password": os.getenv("DB_PASSWORD"),
}

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def clean_keyword(s) -> str:
    if not s or pd.isna(s):
        return ""
    return str(s).replace("/", " ").strip().lower()


def main():
    print("✅ 加载 brand 表...")
    with psycopg2.connect(**DB_CONFIG) as conn:
        query = """
        SELECT name, ch_name, syn_name, en_name, category_id
        FROM brand
        WHERE category_id IS NOT NULL AND category_id != ''
        """
        df = pd.read_sql(query, conn)
    
    print(f"✅ 共 {len(df)} 条品牌记录")

    brand_map = defaultdict(set)
    for _, row in df.iterrows():
        keywords = set()
        for field in [row["name"], row["ch_name"], row["syn_name"], row["en_name"]]:
            cleaned = clean_keyword(field)
            if cleaned:
                for part in cleaned.split():
                    if part.strip():
                        keywords.add(part.strip())
        
        cat_id = int(row["category_id"])
        for kw in keywords:
            brand_map[kw].add(cat_id)
    
    result = {k: list(v) for k, v in brand_map.items()}
    output_path = OUTPUT_DIR / "brand_keyword_map.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False)
    
    print(f"✅ 品牌关键词映射已保存至: {output_path}")
    print(f"✅ 共 {len(result)} 个唯一关键词")


if __name__ == "__main__":
    main()
