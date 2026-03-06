# main_pipeline/main_controller.py
import os
import time
import traceback
import pandas as pd
import numpy as np
from datetime import datetime, date
import urllib.parse
import concurrent.futures

from db_utils import fetch_goods_procurements, fetch_total_count, fetch_processed_records
from .database_writer import DatabaseWriter
from .processor_core import ProcessorCore
from file_downloader import download_attachments
from document_processor import extract_text_enhanced
from rag_retriever import get_similar_cases
from llm_client import call_qwen3
from output_formatter import parse_llm_output
from db_item_parser import parse_db_items_strict
from attachment_enhancer import enhance_with_attachment
from prompt_builder import build_enhanced_prompt
from procurement_classifier import classify_procurement_type
from item_post_processor import post_process_items
from project_category_classifier import validate_and_classify
from commodity_enhancer import enhance_commodity_extraction

class MainController:
    """主控制器，协调整个批处理流程"""
    
    def __init__(self, batch_size=10, skip_processed=True, cleanup_files=True):
        self.batch_size = batch_size
        self.skip_processed = skip_processed
        self.cleanup_files = cleanup_files
        self.db_writer = DatabaseWriter()
        self.processor = ProcessorCore(self.db_writer)
        self.record_timeout = 1800  # 单条记录超时 30分钟

    def _mark_record_as_failed(self, row, reason):
        """
        【关键修复】将失败/超时的记录标记写入数据库
        防止下一轮循环重复抓取该"毒药"数据
        """
        try:
            if not self.db_writer or not self.db_writer.is_connected():
                return

            proc_id = int(row['procurement_id'])
            proj_num = str(row['project_number'])
            
            # 构建一个占位记录，确保它出现在 procurement_commodity_category 表中
            # 这样 db_utils 的 SQL (NOT IN) 就会排除它
            failed_record = {
                "procurement_id": proc_id,
                "project_number": proj_num,
                "project_name": str(row.get('project_name', 'Unknown')),
                "procurement_type": "error_skipped", # 标记为错误跳过
                "commodity_category": "处理失败",
                "items_data": [], # 空商品
                "raw_llm_output": f"Processing Failed: {reason}",
                "processing_log": {
                    "error": reason, 
                    "timestamp": datetime.now().isoformat(),
                    "status": "SKIPPED_TO_PREVENT_LOOP"
                },
                "data_source": "error_handler",
                "created_at": datetime.now()
            }
            
            self.db_writer.insert_procurement_record(failed_record)
            print(f"[ERROR-HANDLE] 🚫 已将项目 {proj_num} 标记为失败，下次将自动跳过。")
            
        except Exception as e:
            print(f"[ERROR-HANDLE] ⚠️ 标记失败记录时出错: {e}")

    def _process_with_timeout(self, row):
        """包装函数：带超时限制 + 失败标记 的单条处理"""
        proj_num = str(row['project_number'])
        
        # 使用线程池来实现超时控制
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(self.process_record, row)
            try:
                # 等待结果，最长 self.record_timeout 秒
                return future.result(timeout=self.record_timeout)
            except concurrent.futures.TimeoutError:
                print(f"\n[TIMEOUT] ⏳ 严重警告: 项目 {proj_num} 处理耗时超过 {self.record_timeout/60} 分钟！")
                print(f"[TIMEOUT] 🛑 强制跳过该项目，并写入失败记录...")
                # 【修复】超时必须写入数据库标记
                self._mark_record_as_failed(row, "Timeout (30m) - Skipped")
                return False
            except Exception as e:
                print(f"[ERROR] 线程执行异常: {e}")
                # 【修复】未知异常也写入数据库标记，防止死循环
                self._mark_record_as_failed(row, f"Exception: {str(e)}")
                return False
    
    def process_record(self, row: pd.Series) -> bool:
        """处理单个记录"""
        try:
            # 提取基本信息
            proc_id = int(row['procurement_id'])
            proj_num = str(row['project_number'])
            proj_name = str(row['project_name'])
            
            print(f"\n{'='*60}")
            print(f"[MAIN] 📦 开始处理项目: {proj_num} - {proj_name} (ID: {proc_id})")
            start_time = time.time()
            
            # 1. 检查是否已处理过
            if self.skip_processed and self.db_writer and self.db_writer.is_connected():
                exists = self.db_writer.check_record_exists(proc_id)
                if exists:
                    print(f"[MAIN] 🔄 记录已存在，跳过: {proj_num}")
                    return True
            
            # 2. 下载附件
            urls = self._extract_urls(row.get("related_links"))
            print(f"[DOWNLOAD] 🔄 原始URL: {len(urls)} → 去重后: {len(list(dict.fromkeys(urls)))}")
            attachment_paths = download_attachments(urls, proj_name)
            print(f"[DOWNLOAD] 📥 下载 {len(attachment_paths)} 个附件")
            
            # 3. 提取附件文本
            full_attachment_text = ""
            if attachment_paths:
                full_attachment_text = self.processor.extract_attachment_text(attachment_paths, proj_name)
                print(f"[EXTRACT] ✅ 附件提取完成: {len(full_attachment_text)} 字符")
            
            # 4. 解析DB项目
            record_dict = self._series_to_dict(row)
            db_items = parse_db_items_strict(record_dict)
            
            if not db_items or len(db_items) == 0:
                print(f"[WARN] ⚠️ DB中无有效商品信息")
                db_items = [{
                    "商品名称": proj_name[:100],
                    "规格型号": "未指定",
                    "采购数量": "1",
                    "单位": "项"
                }]
            
            print(f"[DB] ✅ 解析出 {len(db_items)} 个商品")
            
            # 5. 采购类型分类
            doc_type = classify_procurement_type(proj_name, full_attachment_text, record_dict)
            print(f"[CLASSIFY] 📋 采购类型: {doc_type}")
            
            # 6. 项目分类
            commodity_names = [item.get("商品名称", "") for item in db_items]
            commodity_category = "其他"
            try:
                commodity_category = validate_and_classify(
                    project_name=proj_name,
                    commodity_names=commodity_names,
                    description=full_attachment_text[:500] if full_attachment_text else "",
                    use_llm=True
                )
            except:
                print(f"[CATEGORY] ⚠️ 分类失败，使用默认分类")
            
            print(f"[CATEGORY] 🏷️ 商品分类: {commodity_category}")
            
            # 7. 使用附件信息增强
            final_items = db_items
            llm_output = "无附件，直接使用DB解析"
            
            if attachment_paths and full_attachment_text.strip():
                try:
                    # RAG检索
                    requirement_text = f"{proj_name} " + " ".join([item.get('商品名称', '') for item in db_items])
                    similar_cases = get_similar_cases(requirement_text, min_similarity_threshold=0.3)
                    print(f"[RAG] 🔍 检索到 {len(similar_cases)} 个案例")
                    
                    # 构建提示词
                    enhanced_items = enhance_with_attachment(db_items, full_attachment_text)
                    prompt = build_enhanced_prompt(enhanced_items, full_attachment_text, similar_cases, doc_type)
                    
                    # 调用LLM
                    llm_response = call_qwen3(prompt)
                    
                    if llm_response and llm_response.strip():
                        print(f"[LLM] 🤖 LLM返回长度: {len(llm_response)} 字符")
                        
                        llm_items = parse_llm_output(llm_response)
                        print(f"[LLM] 🔄 解析出 {len(llm_items)} 个LLM项目")
                        
                        try:
                            enhanced_llm_items = enhance_commodity_extraction(llm_items, full_attachment_text)
                            llm_items = enhanced_llm_items
                        except Exception as e:
                            print(f"[ENHANCE] ⚠️ 商品提取增强失败: {e}")
                        
                        final_items = self._merge_llm_db_items(llm_items, enhanced_items)
                        llm_output = llm_response[:2000]
                        final_items = post_process_items(final_items, doc_type)
                        print(f"[POST] ✅ 后处理完成，共 {len(final_items)} 项")
                    else:
                        print(f"[LLM] ⚠️ LLM返回空结果，使用DB解析")
                        llm_output = "LLM返回空结果"
                        
                except Exception as llm_error:
                    print(f"[LLM] ⚠️ LLM处理失败: {llm_error}")
                    llm_output = f"LLM处理失败: {str(llm_error)[:200]}"
            
            print(f"[ITEMS] 📊 最终商品数量: {len(final_items)} 项")
            
            # 8. 构建处理日志
            log_info = {
                "attachment_count": len(attachment_paths),
                "text_length": len(full_attachment_text),
                "item_count": len(final_items),
                "duration_sec": round(time.time() - start_time, 2),
                "processing_time": datetime.now().isoformat()
            }
            
            # 9. 准备项目信息
            proc_info = {
                "procurement_id": proc_id,
                "project_number": proj_num,
                "project_name": proj_name,
                "procurement_type": doc_type,
                "commodity_category": commodity_category
            }
            
            # 10. 转换为数据库格式
            try:
                db_record = self.processor.transform_to_db_format(
                    proc_info=proc_info,
                    final_items=final_items,
                    llm_output=llm_output,
                    log_info=log_info
                )
                
                # 11. 写入数据库
                if self.db_writer and self.db_writer.is_connected():
                    success = self.db_writer.insert_procurement_record(db_record)
                    if success:
                        print(f"[DB] ✅ 项目记录写入成功: {proj_num}")
                    else:
                        print(f"[DB] ❌ 项目记录写入失败")
                        # 写入失败也要记录，避免死循环
                        return False
                else:
                    print(f"[DB] ⚠️ 数据库未连接，跳过写入")
                    return False
                
            except Exception as db_error:
                print(f"[DB] ❌ 数据库记录转换失败: {db_error}")
                return False
            
            # 12. 保存JSON备份
            try:
                json_path = self.processor.save_to_json(
                    proc_info=proc_info,
                    items=final_items,
                    llm_output=llm_output,
                    log_info=log_info
                )
                if json_path:
                    print(f"[BACKUP] 💾 JSON备份已保存: {json_path}")
            except Exception as json_error:
                print(f"[BACKUP] ⚠️ JSON保存失败: {json_error}")
            
            # 13. 清理文件
            if self.cleanup_files and attachment_paths:
                print(f"[CLEANUP] 🗑️ 开始清理项目文件...")
                self.processor.cleanup_project_files(attachment_paths, proc_info)
            
            print(f"[MAIN] ✅ 处理完成，耗时: {time.time() - start_time:.2f}秒")
            return True
            
        except Exception as e:
            error_detail = traceback.format_exc()[:500]
            print(f"[ERROR] ❗ 处理失败: {str(e)}")
            # 抛出异常以便 _process_with_timeout 捕获并记录失败
            raise e
    
    def _series_to_dict(self, series):
        """将pandas Series转换为普通字典"""
        result = {}
        for key in series.index:
            value = series[key]
            if isinstance(value, (datetime, date)):
                result[key] = value.isoformat()
            elif hasattr(value, '__len__') and not isinstance(value, (str, bytes)):
                if len(value) == 0: result[key] = None
                elif isinstance(value, np.ndarray):
                    if value.size == 0: result[key] = None
                    elif value.size == 1: result[key] = str(value.item()) if not pd.isna(value.item()) else None
                    else:
                        try: result[key] = str(value.tolist())
                        except: result[key] = None
                else:
                    try: result[key] = str(list(value))
                    except: result[key] = None
            elif pd.isna(value) or value is None:
                result[key] = None
            else:
                result[key] = value
        return result
    
    def _extract_urls(self, raw_urls):
        import json
        if isinstance(raw_urls, str):
            try: urls = json.loads(raw_urls)
            except: urls = [url.strip() for url in raw_urls.split(',') if url.strip()]
        elif isinstance(raw_urls, list): urls = raw_urls
        else: urls = []
        decoded_urls = []
        for url in urls:
            try: decoded = urllib.parse.unquote(url)
            except: decoded = url
            decoded_urls.append(decoded)
        return list(dict.fromkeys(decoded_urls))
    
    def _merge_llm_db_items(self, llm_items, db_items):
        """智能合并LLM和DB的结果 - 【核心修复】基于名称精准匹配"""
        if not llm_items or not isinstance(llm_items, list):
            return db_items
            
        # 场景A：极端情况 - 数据库只有1项（总包），LLM从附件拆分出多项
        if len(db_items) == 1 and len(llm_items) > 1:
            print(f"[MERGE] ⚡ 识别到总包项目 (DB仅 1 项，LLM有 {len(llm_items)} 项)，直接采用LLM明细")
            db_ref = db_items[0]
            merged = []
            for llm_item in llm_items:
                if not isinstance(llm_item, dict): continue
                merged_item = llm_item.copy()
                if not merged_item.get("建议品牌") and db_ref.get("建议品牌") not in ["", "-", "无", "无要求"]:
                    merged_item["建议品牌"] = db_ref["建议品牌"]
                merged.append(merged_item)
            return merged

        # 场景B：常规情况 - 【拒绝盲目按顺序合并，改为按名称匹配】
        print(f"[MERGE] 🔄 启动精准名称匹配: LLM({len(llm_items)}项) vs DB({len(db_items)}项)")
        merged = []
        used_llm_indices = set()
        
        for db_item in db_items:
            db_name = str(db_item.get("商品名称", "")).strip()
            merged_item = db_item.copy()
            best_match_idx = -1
            
            # 1. 尝试精确名称匹配
            for i, llm_item in enumerate(llm_items):
                if i in used_llm_indices: continue
                if db_name == str(llm_item.get("商品名称", "")).strip():
                    best_match_idx = i
                    break
                    
            # 2. 如果精确匹配不到，尝试互相包含匹配（模糊）
            if best_match_idx == -1:
                for i, llm_item in enumerate(llm_items):
                    if i in used_llm_indices: continue
                    llm_name = str(llm_item.get("商品名称", "")).strip()
                    # 比如 DB是"胶棉拖把"，LLM是"拖把"，互相包含即算匹配
                    if (db_name and llm_name) and (db_name in llm_name or llm_name in db_name):
                        best_match_idx = i
                        break
            
            # 3. 将匹配到的LLM规格赋予DB商品
            if best_match_idx != -1:
                matched_llm = llm_items[best_match_idx]
                used_llm_indices.add(best_match_idx)
                
                # 提取规格和备注
                if matched_llm.get("规格型号"):
                    merged_item["规格型号"] = matched_llm["规格型号"]
                if matched_llm.get("备注"):
                    merged_item["备注"] = matched_llm["备注"]
                    
                # 补充品牌
                if not merged_item.get("建议品牌") and matched_llm.get("建议品牌"):
                    merged_item["建议品牌"] = matched_llm["建议品牌"]
                    
                # 修复数量为空的情况
                llm_qty = str(matched_llm.get("采购数量", "")).strip()
                db_qty = str(merged_item.get("采购数量", "")).strip()
                if llm_qty and (not db_qty or db_qty == "1" or db_qty == "0"):
                    merged_item["采购数量"] = llm_qty
                    
                if not merged_item.get("单位") and matched_llm.get("单位"):
                    merged_item["单位"] = matched_llm["单位"]
            else:
                # 没匹配到（说明附件里可能没写规格），保持原样，千万不能乱套别人的规格！
                pass
            
            # 无论是否匹配到规格，都把DB里有的商品加入结果列表
            merged.append(merged_item)
            
        # 4. 把 LLM 里额外提取出来（但在DB里没找到名字）的隐藏项追加在后面，防止丢单
        for i, llm_item in enumerate(llm_items):
            if i not in used_llm_indices:
                merged.append(llm_item)
                
        return merged
    
    def run(self, max_batches=None):
        """运行批处理"""
        print("=" * 60)
        print("[CONTROLLER] 🚀 启动批量处理pipeline...")
        total_records = fetch_total_count()
        print(f"[CONTROLLER] 📊 待处理记录数: {total_records}")
        if total_records == 0:
            print("[CONTROLLER] ✅ 没有新记录需要处理")
            return
        offset = 0
        batch_count = 0
        while True:
            if max_batches and batch_count >= max_batches:
                print(f"[CONTROLLER] 🛑 已达到最大批次限制 ({max_batches})，主动退出循环")
                break
            print(f"\n{'='*60}")
            current_offset = 0 
            print(f"[CONTROLLER] 📥 加载第 {batch_count + 1} 批 (Limit {self.batch_size})...")
            df = fetch_goods_procurements(limit=self.batch_size, offset=current_offset)
            if df.empty:
                print(f"[CONTROLLER] ✅ 所有记录处理完成")
                break
            for idx, row in df.iterrows():
                # 【修改】使用带超时机制的调用
                self._process_with_timeout(row)
            batch_count += 1
            if len(df) < self.batch_size:
                break
        if self.db_writer:
            self.db_writer.close()
        print(f"\n[CONTROLLER] 本次运行结束，共处理 {batch_count} 批")