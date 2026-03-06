# main_pipeline.py
import os
import json
import time
import traceback
from datetime import datetime
import pandas as pd
from typing import List, Dict
import warnings
from pathlib import Path

# 修复tokenizers并行性警告
os.environ["TOKENIZERS_PARALLELISM"] = "false"

from db_utils import fetch_goods_procurements
from file_downloader import download_attachments
from document_processor import extract_text
from rag_retriever import get_similar_cases
from llm_client import call_qwen3
from output_formatter import parse_llm_output
from db_item_parser import parse_db_items_strict
from attachment_enhancer import enhance_with_attachment
from prompt_builder import build_enhanced_prompt
from procurement_classifier import classify_procurement_type
from item_post_processor import post_process_items
from document_processor import extract_text_enhanced  # 新增导入
from attachment_enhancer import enhance_with_attachment_comprehensive


def extract_text_with_table_enhancement(pdf_path: Path) -> str:
    """增强表格识别的文本提取"""
    try:
        import pdfplumber
        full_text = ""
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                # 优先提取表格
                tables = page.extract_tables()
                for table in tables:
                    table_text = ""
                    for row in table:
                        if any(cell and str(cell).strip() for cell in row):
                            row_text = " | ".join([str(cell) if cell else "" for cell in row])
                            table_text += row_text + "\n"
                    if table_text.strip():
                        full_text += "【表格开始】\n" + table_text + "【表格结束】\n"
                
                # 提取普通文本
                text = page.extract_text()
                if text:
                    full_text += text + "\n"
        
        return full_text.strip()
    except Exception as e:
        print(f"[EXTRACT] ⚠️ 表格增强提取失败: {e}")
        # 回退到普通提取
        try:
            from document_processor import extract_text_native
            return extract_text_native(pdf_path)
        except:
            return ""

def _merge_llm_db_items(llm_items: List[Dict], db_items: List[Dict]) -> List[Dict]:
    """
    智能合并LLM和DB的结果 - 修复版
    策略：
    1. 当LLM拆分出更多明细时，以LLM结构为主，并从DB继承通用属性（品牌、备注）。
    2. 当LLM项数少于或等于DB时，以LLM数据为最高优先级进行一对一合并，DB仅作兜底补充。
    """
    if not llm_items or not isinstance(llm_items, list):
        return db_items
        
    merged = []
    
    # 情况A：LLM拆分出了更多明细（例如：DB是"家具一批"，LLM是"桌子、椅子..."）
    # 判定标准：LLM项目数 > DB项目数
    if len(llm_items) > len(db_items):
        print(f"[MERGE] ⚡ LLM拆分出 {len(llm_items)} 项 (DB仅 {len(db_items)} 项)，采用LLM结构并继承DB属性")
        
        # 1. 准备要继承的DB全局属性 (仅当DB只有1项时，视为全局属性，可以安全继承)
        global_props = {}
        if len(db_items) == 1:
            db_ref = db_items[0]
            # 如果DB有品牌，且不为空/无效值，记下来
            if db_ref.get("建议品牌") and db_ref["建议品牌"] not in ["-", "无", "无要求", "None", ""]:
                global_props["建议品牌"] = db_ref["建议品牌"]
            # 如果DB有重要备注，记下来
            if db_ref.get("备注"):
                global_props["db_remark"] = db_ref["备注"]

        for llm_item in llm_items:
            if not isinstance(llm_item, dict):
                continue
                
            # 2. 基础结构直接使用 LLM 的 (深拷贝以防修改原数据)
            merged_item = {}
            for field in ["商品名称", "规格型号", "建议品牌", "采购数量", "单位", "备注"]:
                merged_item[field] = llm_item.get(field, "")
            
            # 3. 补全品牌 (如果LLM没识别到，但DB里有全局品牌，就继承DB的)
            # 例如：DB说品牌是"联想"，LLM拆出了"主机"和"显示器"但没写品牌，这里自动填上"联想"
            if not merged_item.get("建议品牌") and "建议品牌" in global_props:
                merged_item["建议品牌"] = global_props["建议品牌"]
                
            # 4. 智能合并备注 (保留LLM备注，追加DB备注)
            if "db_remark" in global_props:
                current_note = merged_item.get("备注", "")
                db_note = global_props["db_remark"]
                # 避免重复内容
                if db_note and db_note not in current_note:
                    if current_note:
                        merged_item["备注"] = f"{current_note} (DB备注: {db_note})"
                    else:
                        merged_item["备注"] = db_note

            # 5. 数量兜底 (仅当LLM完全没提取到数量时，尝试去DB匹配)
            if not merged_item.get("采购数量"):
                llm_name = merged_item.get("商品名称", "")
                for db_item in db_items:
                    # 简单的包含匹配
                    if db_item.get("商品名称", "") in llm_name or llm_name in db_item.get("商品名称", ""):
                        if db_item.get("采购数量"):
                            merged_item["采购数量"] = db_item.get("采购数量")
                        if not merged_item.get("单位") and db_item.get("单位"):
                            merged_item["单位"] = db_item.get("单位")
                        break
            
            merged.append(merged_item)
            
    else:
        # 情况B：LLM返回单一项目，或项目数少于DB
        # 策略：以LLM为主，因为附件解析出来的数据更贴近真实的明细要求
        print(f"[MERGE] 🔄 LLM项数({len(llm_items)}) <= DB项数({len(db_items)})，尝试常规合并(LLM优先)")
        
        for i in range(max(len(llm_items), len(db_items))):
            llm_item = llm_items[i] if i < len(llm_items) else {}
            db_item = db_items[i] if i < len(db_items) else {}
            
            merged_item = {}
            for field in ["商品名称", "规格型号", "建议品牌", "采购数量", "单位", "备注"]:
                # 修复核心逻辑：永远优先使用 LLM 解析出来的附件内容
                if llm_item.get(field):
                    merged_item[field] = llm_item[field]
                # 当 LLM 没有提取到该字段时，才使用 DB 里的内容做兜底补充
                elif db_item.get(field):
                    merged_item[field] = db_item[field]
                else:
                    merged_item[field] = ""
                    
            merged.append(merged_item)
    
    return merged

def _save_result(record, items, llm_output, log_info, commodity_category="其他"):
    """保存处理结果"""
    output = {
        "procurement_id": int(record["procurement_id"]),
        "project_number": record['project_number'],
        "project_name": record['project_name'],
        "procurement_type": "goods",  # 简化，实际应从分类器获取
        "commodity_category": commodity_category,  # 新增字段
        "generated_items": items,
        "raw_llm_output": llm_output,
        "processing_log": {
            "start_time": datetime.now().isoformat(),
            **log_info
        }
    }
    
    os.makedirs("outputs", exist_ok=True)
    output_path = f"outputs/{record['project_number']}.json"
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[SAVE] 💾 结果保存至: {output_path}")

def _save_error(proj_num, error_msg, error_detail=None):
    """保存错误信息"""
    error_log = {
        "project_number": proj_num,
        "error": error_msg,
        "error_detail": error_detail,
        "timestamp": datetime.now().isoformat()
    }
    os.makedirs("outputs", exist_ok=True)
    error_path = f"outputs/{proj_num}_ERROR.json"
    with open(error_path, 'w', encoding='utf-8') as f:
        json.dump(error_log, f, ensure_ascii=False, indent=2)
    print(f"[ERROR] ❗ 错误保存至: {error_path}")

def get_commodity_category(proj_name: str, attachment_text: str, db_items: List[Dict]) -> str:
    """获取商品分类（新增函数）"""
    try:
        # 尝试导入新版的分类器
        try:
            from project_category_classifier import validate_and_classify
            # 从商品列表中提取商品名称
            commodity_names = []
            if db_items:
                for item in db_items:
                    if isinstance(item, dict) and item.get("商品名称"):
                        commodity_names.append(item["商品名称"])
            
            # 使用严格分类函数
            category = validate_and_classify(
                project_name=proj_name,
                commodity_names=commodity_names,
                description=attachment_text[:500] if attachment_text else "",
                use_llm=True
            )
            return category
            
        except ImportError:
            # 尝试使用旧版函数
            try:
                from project_category_classifier import classify_project
                category = classify_project(
                    project_name=proj_name,
                    attachment_text=attachment_text,
                    db_items=db_items,
                    use_llm=True
                )
                return category
            except ImportError:
                # 使用简单分类
                return "其他"
                
    except Exception as e:
        print(f"[CATEGORY] ⚠️ 商品分类失败: {e}")
        # 使用备用分类策略
        return _fallback_category_classification(proj_name, db_items)

def _fallback_category_classification(proj_name: str, db_items: List[Dict]) -> str:
    """备用分类策略"""
    if not db_items:
        return "服务与其他"
    
    # 提取所有商品名称文本
    item_text = proj_name.lower()
    for item in db_items:
        if isinstance(item, dict):
            item_text += " " + item.get("商品名称", "").lower()
    
    # 简单的关键词匹配
    category_keywords = {
        "行政办公耗材": ["打印纸", "文具", "笔", "文件夹", "档案", "办公用品"],
        "清洁日化用品": ["洗手液", "消毒液", "洗衣液", "纸巾", "清洁", "洗涤"],
        "数码家电": ["电脑", "空调", "打印机", "微波炉", "冰箱", "手机"],
        "体育器材与服装": ["体育", "运动", "篮球", "排球", "羽毛球", "服装", "运动鞋"],
        "专业设备与工业品": ["消防", "工程", "机械", "设备", "仪器", "工具", "安防"],
        "食品与饮品": ["食品", "饮料", "牛奶", "油", "米", "面", "饼干"],
    }
    
    for category, keywords in category_keywords.items():
        for keyword in keywords:
            if keyword.lower() in item_text:
                return category
    
    return "服务与其他"

def process_single_record(record: pd.Series):
    """处理单个采购记录 - 修复版"""
    proj_num = record['project_number']
    proj_name = record['project_name']
    print(f"\n{'='*60}")
    print(f"[MAIN] 📦 开始处理: {proj_num} - {proj_name}")
    start_time = time.time()
    
    try:
        # 1. 下载附件 - 去重处理
        raw_urls = record["related_links"]
        if isinstance(raw_urls, str):
            # 如果是字符串，尝试解析（可能是JSON字符串）
            try:
                urls = json.loads(raw_urls)
            except:
                # 如果是逗号分隔的字符串
                urls = [url.strip() for url in raw_urls.split(',') if url.strip()]
        elif isinstance(raw_urls, list):
            urls = raw_urls
        else:
            urls = []
            
        # URL去重
        unique_urls = list(dict.fromkeys(urls))
        attachment_paths = download_attachments(unique_urls, proj_name)
        print(f"[DOWNLOAD] ✅ 下载 {len(attachment_paths)} 个附件")
        
        # 2. 提取附件文本 - 修复：避免重复调用
        processed_files = set()  # 避免重复处理相同文件
        attachment_texts = []
        
        for path in attachment_paths:
            file_hash = os.path.basename(path)  # 简单的文件名去重
            if file_hash not in processed_files:
                # ================= 关键修复：只调用一次 =================
                try:
                    # 直接使用 extract_text_enhanced，不要有回退调用
                    text = extract_text_enhanced(path, proj_name)
                    # 如果文本内容很少或为空，说明提取可能有问题
                    if text and len(text.strip()) < 100:
                        print(f"[EXTRACT] ⚠️ 提取内容较少 ({len(text.strip())} 字符)")
                        # 但仍然使用这个结果，不要回退到 extract_text
                    
                except Exception as e:
                    print(f"[EXTRACT] ⚠️ 增强提取失败: {e}")
                    text = ""  # 设置为空，而不是调用 extract_text
                # ================= 修复结束 =================
                    
                if text and text.strip():
                    attachment_texts.append(text)
                    print(f"[EXTRACT] ✅ 文件 {os.path.basename(path)} 提取成功: {len(text.strip())} 字符")
                else:
                    print(f"[EXTRACT] ⚠️ 文件 {os.path.basename(path)} 无有效内容")
                    
                processed_files.add(file_hash)
            else:
                print(f"[EXTRACT] 🔄 跳过重复文件: {os.path.basename(path)}")
                
        full_attachment_text = "\n".join(attachment_texts)
        print(f"[EXTRACT] ✅ 所有附件提取完成，总长度: {len(full_attachment_text)} 字符")
        
        # 3. 打印附件文本预览（用于调试）
        if full_attachment_text.strip():
            preview = full_attachment_text[:500] + "..." if len(full_attachment_text) > 500 else full_attachment_text
            print(f"[EXTRACT] 📋 文本预览: {preview}")
        
        # 4. 严格解析DB项目（核心）
        db_items = parse_db_items_strict(record.to_dict())
        if not db_items:
            print(f"[WARN] ❌ DB中无有效商品信息")
            _save_result(record, [], "DB中无有效商品信息", {
                "attachment_count": len(attachment_paths),
                "text_length": len(full_attachment_text),
                "case_count": 0,
                "duration_sec": round(time.time() - start_time, 2)
            })
            return
        
        print(f"[DB] ✅ 解析出 {len(db_items)} 个商品:")
        for i, item in enumerate(db_items, 1):
            print(f"      {i}. {item['商品名称']} × {item['采购数量']}{item['单位']}")
        
        # 5. 使用附件信息增强（不覆盖）
        enhanced_items = enhance_with_attachment(db_items, full_attachment_text)
        
        # 6. 采购类型分类
        doc_type = classify_procurement_type(proj_name, full_attachment_text, record.to_dict())
        print(f"[CLASSIFY] ✅ 识别为: {doc_type}")
        
        # 7. 项目分类（更新版） - 使用新函数
        commodity_category = get_commodity_category(
            proj_name=proj_name,
            attachment_text=full_attachment_text,
            db_items=enhanced_items
        )
        print(f"[CATEGORY] ✅ 商品分类为: {commodity_category}")
        
        # 8. RAG检索
        requirement_text = f"{proj_name} " + " ".join([item.get('商品名称', '') for item in enhanced_items])
        similar_cases = get_similar_cases(requirement_text, min_similarity_threshold=0.3)
        print(f"[RAG] ✅ 检索到 {len(similar_cases)} 个案例")
        
        # 9. LLM处理（只有有附件时才调用）
        if attachment_paths and full_attachment_text.strip():
            print(f"[LLM] 📝 调用LLM增强处理...")
            try:
                # 先尝试使用表格感知的提示词
                from prompt_builder import build_table_aware_prompt
                prompt = build_table_aware_prompt(enhanced_items, full_attachment_text, similar_cases, doc_type)
                print(f"[PROMPT] 📋 使用表格感知提示词")
            except ImportError:
                # 回退到原有提示词
                from prompt_builder import build_enhanced_prompt
                prompt = build_enhanced_prompt(enhanced_items, full_attachment_text, similar_cases, doc_type)
                print(f"[PROMPT] 📋 使用标准增强提示词")
            
            # 打印提示词预览（调试用）
            print(f"[LLM] 💬 提示词长度: {len(prompt)} 字符")
            if len(prompt) > 1000:
                print(f"[LLM] 📋 提示词预览: {prompt[:500]}...")
            
            llm_output = call_qwen3(prompt)
            
            if llm_output and llm_output.strip():
                print(f"[LLM] ✅ LLM返回长度: {len(llm_output)} 字符")
                print(f"[LLM] 📄 LLM输出预览: {llm_output[:300]}...")
                
                # 原有的解析
                llm_items = parse_llm_output(llm_output)
                print(f"[LLM] 🔄 解析出 {len(llm_items)} 个LLM项目")
                
                # 新增：商品提取增强
                try:
                    from prompt_builder import enhance_commodity_extraction
                    enhanced_llm_items = enhance_commodity_extraction(llm_items, full_attachment_text)
                    llm_items = enhanced_llm_items  # 使用增强后的结果
                    print(f"[ENHANCE] ✅ 商品名称和规格已优化")
                except Exception as e:
                    print(f"[ENHANCE] ⚠️ 商品提取增强失败: {e}")
                
                # LLM结果与DB结果智能合并
                final_items = _merge_llm_db_items(llm_items, enhanced_items)
            else:
                print(f"[LLM] ⚠️ LLM返回空结果，使用DB解析")
                final_items = enhanced_items
                llm_output = "LLM返回空结果，使用DB解析"
        else:
            print(f"[LLM] ⚠️ 无附件或附件无文本，直接使用DB解析")
            final_items = enhanced_items
            llm_output = "无附件，直接使用DB解析"
            
        # 10. 后处理
        final_items = post_process_items(final_items, doc_type)
        
        # ============ 新增：最终优化处理 ============
        final_items = _post_process_items_before_save(final_items, full_attachment_text)
        
        print(f"[POST] ✅ 后处理完成，共 {len(final_items)} 项:")
        for i, item in enumerate(final_items, 1):
            print(f"      {i}. {item['商品名称']} × {item.get('采购数量', '?')}{item.get('单位', '')}")
        
        # 11. 保存结果
        _save_result(record, final_items, llm_output, {
            "attachment_count": len(attachment_paths),
            "text_length": len(full_attachment_text),
            "case_count": len(similar_cases),
            "duration_sec": round(time.time() - start_time, 2)
        }, commodity_category)  # 传入项目分类
        
        print(f"[MAIN] ✅ 处理完成，耗时: {time.time() - start_time:.2f}秒")
        
    except Exception as e:
        # 显示详细错误信息
        error_detail = traceback.format_exc()
        print(f"[ERROR] ❗ 处理失败: {e}")
        print(f"[ERROR] 🔍 详细错误:\n{error_detail}")
        _save_error(proj_num, str(e), error_detail)
def _post_process_items_before_save(items: List[Dict], attachment_text: str) -> List[Dict]:
    """保存前的最终后处理 - 修复评估中发现的问题"""
    processed_items = []
    
    for item in items:
        processed_item = item.copy()
        
        # 1. 优化商品名称
        if "商品名称" not in processed_item or not processed_item["商品名称"]:
            if "规格型号" in processed_item:
                # 从规格型号中提取商品名称
                processed_item["商品名称"] = _extract_commodity_name_from_specs(
                    processed_item["规格型号"]
                )
        
        # 2. 清理品牌字段
        if "建议品牌" in processed_item:
            processed_item["建议品牌"] = _clean_brand_field(processed_item["建议品牌"])
        
        # 3. 优化规格型号
        if "规格型号" in processed_item:
            # 移除"核心参数要求:"前缀，提取关键信息
            specs = processed_item["规格型号"]
            if specs.startswith("核心参数要求:"):
                # 提取关键规格信息
                processed_item["规格型号"] = _optimize_specifications(specs)
        
        # 4. 修正通用商品名称
        current_name = processed_item.get("商品名称", "")
        if current_name in ["打印/复印纸", "医药卫生类", "读卡产品", "收发器", "综合零售服务"]:
            # 尝试从附件中获取更具体的商品名称
            if attachment_text:
                better_name = _find_better_name_in_attachment(current_name, attachment_text)
                if better_name:
                    processed_item["商品名称"] = better_name
        
        # 5. 标准化单位
        if processed_item.get("单位") in ["件", "个", "批"]:
            # 根据商品名称推断更准确的单位
            better_unit = _infer_better_unit_from_name(processed_item.get("商品名称", ""))
            if better_unit:
                processed_item["单位"] = better_unit
        
        processed_items.append(processed_item)
    
    return processed_items
def _extract_commodity_name_from_specs(spec_model: str) -> str:
    """从规格型号中提取商品名称"""
    import re
    
    if not spec_model:
        return ""
    
    # 尝试从"核心参数要求"中提取商品类目
    if "核心参数要求:" in spec_model and "商品类目:" in spec_model:
        match = re.search(r'商品类目:\s*([^;]+)', spec_model)
        if match:
            extracted = match.group(1).strip()
            if extracted and extracted not in ["综合零售服务"]:
                return extracted
    
    return ""
def _clean_brand_field(brand_str: str) -> str:
    """清理品牌字段，提取主要品牌"""
    import re
    
    if not brand_str:
        return ""
    
    # 无效品牌标识
    invalid_brands = ["无品牌", "无要求", "无特殊要求", "不限", "-", "无"]
    if brand_str in invalid_brands:
        return ""
    
    # 分割多个品牌
    parts = re.split(r'[/、,，]', brand_str)
    
    # 提取第一个有效品牌
    for part in parts:
        cleaned = part.strip()
        if cleaned and cleaned not in invalid_brands:
            # 清理品牌中的额外描述
            if "/" in cleaned:
                brand_parts = cleaned.split('/')
                return brand_parts[0].strip()
            return cleaned
    
    return ""
def _optimize_specifications(spec_model: str) -> str:
    """优化规格型号格式"""
    import re
    
    if not spec_model:
        return ""
    
    # 如果包含"核心参数要求:"，提取关键信息
    if spec_model.startswith("核心参数要求:"):
        # 提取所有参数
        specs_dict = {}
        
        # 提取键值对
        key_value_pairs = re.findall(r'([^:;]+):\s*([^;]+)', spec_model)
        for key, value in key_value_pairs:
            key_clean = key.strip()
            value_clean = value.strip()
            
            # 跳过不必要的键
            if key_clean not in ["核心参数要求", "商品类目", "描述", "次要参数要求"]:
                specs_dict[key_clean] = value_clean
        
        # 构建简洁的规格字符串
        if specs_dict:
            # 优先显示关键规格
            priority_keys = ["型号", "尺寸", "规格", "颜色分类", "净含量", "包装规格", "销售规格"]
            key_specs = []
            
            for key in priority_keys:
                if key in specs_dict:
                    key_specs.append(f"{key}:{specs_dict[key]}")
            
            if key_specs:
                return "; ".join(key_specs[:3])
    
    return spec_model
def _find_better_name_in_attachment(current_name: str, attachment_text: str) -> str:
    """从附件中查找更好的商品名称"""
    import re
    
    if not attachment_text:
        return current_name
    
    # 根据当前名称查找相关描述
    lines = attachment_text.split('\n')
    
    if current_name == "打印/复印纸":
        for line in lines:
            if "打印纸" in line or "复印纸" in line or "A4" in line:
                if "规格" in line or "型号" in line:
                    match = re.search(r'([^,，。;；\s]{2,20})\s+(打印|复印)纸', line)
                    if match:
                        return f"{match.group(1)}打印/复印纸"
        return "打印/复印纸"
    
    elif current_name == "医药卫生类":
        for line in lines:
            if "负压吸引器" in line or "吸引器" in line:
                return "负压吸引器"
            elif "医疗" in line or "医用" in line:
                match = re.search(r'([^,，。;；\s]{2,20})\s+(设备|器械)', line)
                if match:
                    return match.group(1)
        return "医疗设备"
    
    return current_name
def _infer_better_unit_from_name(commodity_name: str) -> str:
    """根据商品名称推断更准确的单位"""
    if not commodity_name:
        return "个"
    
    name_lower = commodity_name.lower()
    
    # 单位映射
    unit_mapping = [
        (["打印纸", "复印纸", "纸张"], "箱"),
        (["空调", "打印机", "电脑", "服务器", "设备", "器械"], "台"),
        (["办公桌", "会议桌", "桌子"], "张"),
        (["椅子", "办公椅"], "把"),
        (["存储卡", "SD卡", "内存卡"], "张"),
        (["三角架", "三脚架"], "个"),
        (["宣传片", "视频", "拍摄"], "部"),
        (["服务", "项目", "验收"], "项"),
        (["血糖试纸", "试纸"], "盒"),
        (["酒精", "消毒液", "碘伏"], "瓶"),
        (["手套"], "副"),
        (["收纳箱", "塑料桶", "脸盆"], "个"),
        (["床单"], "床"),
        (["毛巾"], "条")
    ]
    
    for keywords, unit in unit_mapping:
        for keyword in keywords:
            if keyword in name_lower:
                return unit
    
    return "个"

def main():
    print("=" * 60)
    print("[SYSTEM] 🚀 启动采购需求智能解析 pipeline...")
    
    # 忽略urllib3警告
    warnings.filterwarnings("ignore", category=UserWarning, module="urllib3")
    
    df = fetch_goods_procurements()
    print(f"[SYSTEM] 📥 加载 {len(df)} 条需求")
    
    success = 0
    for idx, row in df.iterrows():
        try:
            process_single_record(row)
            success += 1
        except Exception as e:
            print(f"[SYSTEM] ⚠️ 跳过项目: {e}")
            continue

    print(f"\n[SUMMARY] 📊 完成: {success}/{len(df)} 个项目")

if __name__ == "__main__":
    main()
