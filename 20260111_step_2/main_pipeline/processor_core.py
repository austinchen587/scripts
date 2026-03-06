# main_pipeline/processor_core.py
import os
import json
import time  # 必须导入 time
import glob  # 必须导入 glob
from datetime import datetime, date
from typing import List, Dict

class JSONEncoder(json.JSONEncoder):
    """自定义JSON编码器，处理datetime和date"""
    def default(self, obj):
        if isinstance(obj, (datetime, date)):
            return obj.isoformat()
        return super().default(obj)

class ProcessorCore:
    """数据处理核心类 - 每个项目一条数据库记录"""
    
    def __init__(self, db_writer=None):
        self.db_writer = db_writer

    def cleanup_project_files(self, attachment_paths: list[str], proc_info: dict):
        """清理项目相关的文件（附件、临时文件等）"""
        if not attachment_paths:
            return
        
        from file_downloader import cleanup_attachments
        cleanup_attachments(attachment_paths)
    
    def extract_attachment_text(self, attachment_paths: list[str], proj_name: str) -> str:
        """
        提取附件文本 - 【修复版：增加超时中断机制】
        防止遇到几百张图片的项目导致卡死
        """
        from document_processor import extract_text_enhanced
        
        processed_files = set()
        attachment_texts = []
        
        # 记录开始时间
        start_time = time.time()
        # 【关键配置】附件提取最大允许时间：300秒 (5分钟)
        # 如果5分钟还没提取完，说明文件太复杂或图片太多，强制停止提取
        MAX_EXTRACT_TIME = 300 
        
        print(f"[EXTRACT] 🚀 开始提取附件 (限时 {MAX_EXTRACT_TIME}秒)...")

        for i, path in enumerate(attachment_paths):
            # 1. 【核心修复】每处理一个文件前，检查是否超时
            current_duration = time.time() - start_time
            if current_duration > MAX_EXTRACT_TIME:
                print(f"\n[EXTRACT] 🛑 附件提取超时！已耗时 {current_duration:.1f}s")
                print(f"[EXTRACT] ⚠️ 跳过剩余 {len(attachment_paths) - i} 个文件，仅使用已提取内容。")
                attachment_texts.append("\n[警告] 附件内容过长，部分内容已截断...")
                break

            file_hash = os.path.basename(path)
            if file_hash not in processed_files:
                try:
                    # 打印进度
                    print(f"[EXTRACT] 📄 ({i+1}/{len(attachment_paths)}) 处理: {file_hash}")
                    
                    text = extract_text_enhanced(path, proj_name)
                    
                    if text and text.strip():
                        attachment_texts.append(text)
                    else:
                        print(f"[EXTRACT] ⚠️ 无有效内容")
                        
                except Exception as e:
                    print(f"[EXTRACT] ⚠️ 提取失败: {e}")
                
                processed_files.add(file_hash)
        
        total_len = sum(len(t) for t in attachment_texts)
        print(f"[EXTRACT] ✅ 附件提取流程结束，总长度: {total_len} 字符")
        return "\n".join(attachment_texts)
    
    def transform_to_db_format(self, proc_info: dict, final_items: List[dict], 
                             llm_output: str, log_info: dict) -> dict:
        """
        将整个项目转换为数据库格式
        每个项目只存一条记录，所有商品存在 items_data 字段中
        """
        try:
            # 清理数据中的datetime对象
            def clean_value(value):
                if isinstance(value, (datetime, date)):
                    return value.isoformat()
                elif value is None:
                    return ""
                return value
            
            # 清理items数据
            cleaned_items = []
            for item in final_items:
                cleaned_item = {}
                for key, value in item.items():
                    cleaned_item[key] = clean_value(value)
                cleaned_items.append(cleaned_item)
            
            # 清理log_info
            cleaned_log = {}
            for key, value in log_info.items():
                cleaned_log[key] = clean_value(value)
            
            # 确定数据来源
            data_source = "llm"
            if llm_output and ("无附件" in llm_output or "LLM返回空结果" in llm_output):
                data_source = "db_enhanced"
            elif not llm_output or "无附件，直接使用DB解析" in llm_output:
                data_source = "db_only"
            
            # 构建数据库记录
            db_record = {
                "procurement_id": int(proc_info.get("procurement_id", 0)),
                "project_number": str(proc_info.get("project_number", "")),
                "project_name": str(proc_info.get("project_name", "")),
                "procurement_type": str(proc_info.get("procurement_type", "goods")),
                "commodity_category": str(proc_info.get("commodity_category", "其他")),
                "items_data": cleaned_items,  # 所有商品存储在这里
                "raw_llm_output": str(llm_output)[:2000] if llm_output else "",
                "processing_log": cleaned_log,
                "data_source": data_source,
                "created_at": datetime.now()
            }
            
            print(f"[PROCESSOR] ✅ 数据库记录已构建: {len(cleaned_items)}个商品")
            return db_record
            
        except Exception as e:
            print(f"[PROCESSOR] ❌ 构建数据库记录失败: {e}")
            raise

    def _cleanup_old_files(self, directory: str, keep_count: int = 20):
        """清理旧文件，只保留最近的 N 个"""
        try:
            files = glob.glob(os.path.join(directory, "*.json"))
            if len(files) <= keep_count:
                return

            files.sort(key=os.path.getmtime, reverse=True)
            files_to_delete = files[keep_count:]
            
            for old_file in files_to_delete:
                try:
                    os.remove(old_file)
                except Exception:
                    pass
                    
        except Exception as e:
            print(f"[CLEANUP] ⚠️ 清理文件出错: {e}")
    
    def save_to_json(self, proc_info: dict, items: List[dict], llm_output: str, log_info: dict):
        """保存结果到JSON文件（备份）"""
        try:
            output = {
                "procurement_id": int(proc_info.get("procurement_id", 0)),
                "project_number": proc_info.get('project_number', ''),
                "project_name": proc_info.get('project_name', ''),
                "procurement_type": proc_info.get('procurement_type', 'goods'),
                "commodity_category": proc_info.get('commodity_category', '其他'),
                "generated_items": items,
                "raw_llm_output": llm_output,
                "processing_log": log_info
            }
            
            os.makedirs("outputs", exist_ok=True)
            project_number = proc_info.get('project_number', 'unknown')
            # 简单的非法字符清理
            safe_filename = "".join([c for c in str(project_number) if c.isalnum() or c in ('-','_')])
            if not safe_filename: safe_filename = "unknown_project"
            
            output_path = f"outputs/{safe_filename}.json"
            
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(output, f, ensure_ascii=False, indent=2, cls=JSONEncoder)
            
            print(f"[PROCESSOR] 💾 JSON已保存: {output_path}")

            # 保存后清理
            self._cleanup_old_files("outputs", keep_count=20)
            
            return output_path
            
        except Exception as e:
            print(f"[PROCESSOR] ⚠️ JSON保存失败: {e}")
            return None
    
    def save_error(self, proj_num: str, error_msg: str, error_detail: str = None):
        """保存错误信息"""
        try:
            error_log = {
                "project_number": proj_num,
                "error": error_msg,
                "error_detail": error_detail[:1000] if error_detail else "",
                "timestamp": datetime.now().isoformat()
            }
            
            os.makedirs("outputs/errors", exist_ok=True)
            
            safe_filename = "".join([c for c in str(proj_num) if c.isalnum() or c in ('-','_')])
            output_path = f"outputs/errors/{safe_filename}_ERROR.json"
            
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(error_log, f, ensure_ascii=False, indent=2, cls=JSONEncoder)
            
            print(f"[PROCESSOR] 💾 错误信息已保存: {output_path}")
            
            # 错误日志也清理
            self._cleanup_old_files("outputs/errors", keep_count=20)
            
        except Exception as e:
            print(f"[PROCESSOR] ⚠️ 错误日志保存失败: {e}")