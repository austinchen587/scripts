import os
import sys
import logging
from pathlib import Path
import pandas as pd
import numpy as np

CACHE_DIR = Path("D:/code/project/scripts/20260110_step_0/.cache")
CACHE_DIR.mkdir(parents=True, exist_ok=True)
os.environ["HF_HOME"] = str(CACHE_DIR / "huggingface")
os.environ["CHROMA_CACHE_DIR"] = str(CACHE_DIR / "chroma")
os.environ["XDG_CACHE_HOME"] = str(CACHE_DIR)

LOG_FILE = Path(__file__).parent / "pipeline.log"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger()

sys.path.append(str(Path(__file__).parent))

from db_utils import fetch_selected_procurements
from file_downloader import download_attachment
from document_processor import process_document
from vectorizer import Text2VecLargeChinese
from vector_store import ProcurementVectorStore
from config import ATTACH_DIR


def extract_urls_from_field(field_value: str) -> list[str]:
    if not field_value or str(field_value).strip().lower() in ['null', 'none', '', '{}']:
        return []
    s = str(field_value).strip()
    if s.startswith('{') and s.endswith('}'):
        s = s[1:-1]
    urls = []
    for part in s.split(','):
        url = part.strip()
        if url and url != 'NULL' and not url.startswith('附件'):
            urls.append(url)
    return urls


def main():
    logger.info("🚀 启动采购 RAG 管道...")

    df = fetch_selected_procurements()
    logger.info(f"📥 从数据库加载 {len(df)} 条记录")

    if df.empty:
        logger.warning("⚠️ 没有 is_selected = true 的记录，退出。")
        return

    # === 新增：按 project_name 分组 ===
    grouped = df.groupby('project_name', sort=False)
    logger.info(f"📦 共 {len(grouped)} 个独立采购项目")

    try:
        vectorizer = Text2VecLargeChinese()
        vector_db = ProcurementVectorStore()
    except Exception as e:
        logger.error(f"❌ 向量模型或数据库初始化失败: {e}")
        return

    all_docs = []
    all_metas = []
    all_ids = []

    # === 按项目处理（不是按行！）===
    for project_name, group in grouped:
        project_number = str(group['project_number'].iloc[0])
        logger.info(f"\n📄 处理项目: {project_name} ({project_number})")

        # 尝试从附件提取统一需求
        extracted_req = ""
        related_links_val = group['related_links'].iloc[0]

        # 处理数组类型
        if isinstance(related_links_val, (list, np.ndarray)):
            related_links_val = related_links_val[0] if len(related_links_val) > 0 else None

        http_links = []
        if pd.notna(related_links_val):
            str_val = str(related_links_val).strip()
            if str_val not in ['', 'null', 'NULL', '{}']:
                extracted_urls = extract_urls_from_field(str_val)
                http_links = [u for u in extracted_urls if u.startswith(('http://', 'https://'))]

        # 下载并分析附件（每个项目最多分析2个）
        if http_links:
            for url in http_links[:2]:
                logger.info(f"  → 下载: {url}")
                local_file = download_attachment(url, project_name)
                if local_file and local_file.exists():
                    logger.info(f"    ✓ 本地路径: {local_file}")
                    try:
                        req_text = process_document(local_file, project_name)
                        if req_text and "本次采购需求为：" in req_text:
                            extracted_req = req_text
                            break
                    except Exception as e:
                        logger.warning(f"    ⚠️ 文档处理失败: {e}")
                else:
                    logger.info(f"    ✗ 附件无效或非文档类型")

        # === 为该项目的每一条商品记录生成向量 ===
        for idx, row in group.iterrows():
            supplier_id = str(row.get('supplier_id', ''))
            commodity_id = str(row.get('commodity_id', '')) or "none"
            record_id = f"{project_number}_{supplier_id}_{commodity_id}"

            def clean_field(val):
                if val is None:
                    return ""
                if isinstance(val, (list, np.ndarray)):
                    items = [str(x) for x in val if not (isinstance(x, float) and pd.isna(x))]
                    return "、".join(items)
                else:
                    if pd.isna(val):
                        return ""
                    s = str(val).strip()
                    if s.startswith('{') and s.endswith('}'):
                        s = s[1:-1]
                    return s.replace('"', '').replace("'", "").strip()

            names = clean_field(row['commodity_names'])
            spec = clean_field(row.get('commodity_specification', ''))
            qty = clean_field(row.get('purchase_quantities', row.get('commodity_quantity', '')))
            brand = clean_field(row.get('suggested_brands', ''))

            fallback_req = (
                f"本次采购需求为：{names}，"
                f"规格：{spec}，"
                f"数量：{qty}，"
                f"品牌要求：{brand}"
            ).replace("  ", " ").strip()

            final_req = extracted_req if extracted_req else fallback_req
            if not final_req:
                logger.warning(f"  ⚠️ 商品 {commodity_id} 无有效需求，跳过")
                continue

            metadata = {
                "project_number": project_number,
                "project_name": project_name,
                "supplier_id": supplier_id,
                "supplier_name": str(row.get('supplier_name', '')),
                "commodity_id": commodity_id,
                "commodity_name": str(row.get('commodity_name', '')),
                "source_type": "visual_extracted" if extracted_req else "structured_fallback"
            }

            all_docs.append(final_req)
            all_metas.append(metadata)
            all_ids.append(record_id)

            logger.info(f"  ✅ 商品 {commodity_id}: {final_req[:80]}...")

    # 4. 生成向量并存入数据库
    if all_docs:
        logger.info(f"\n🧠 正在生成 {len(all_docs)} 条向量...")
        embeddings = vectorizer.encode(all_docs)

        logger.info("💾 存入向量数据库...")
        vector_db.add_documents(
            documents=all_docs,
            metadatas=all_metas,
            ids=all_ids,
            embeddings=embeddings
        )
        logger.info("✅ 全部完成！向量已持久化到本地 ChromaDB。")
    else:
        logger.error("❌ 未生成任何有效采购需求文本。")


if __name__ == "__main__":
    main()
