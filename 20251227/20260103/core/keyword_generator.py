# keyword_generator.py
import logging
import json
import re
from database import DatabaseManager
from file_processor import FileProcessor
from model_engine import ModelEngine

logger = logging.getLogger(__name__)

class KeywordGenerator:
    def __init__(self):
        self.db_manager = DatabaseManager()
        self.file_processor = FileProcessor()
        self.model_engine = ModelEngine()
    
    def process_record(self, record_data):
        """处理单个记录"""
        record_id = record_data['record_id']
        project_name = record_data['project_name']
        downloaded_files = record_data['downloaded_files']
        
        logger.info(f"开始处理记录 record_id={record_id}, project={project_name}")
        
        # 1. 连接数据库并获取采购数据
        if not self.db_manager.connect():
            return self._create_error_result(record_id, "数据库连接失败")
        
        procurement_data = self.db_manager.get_procurement_data(record_id)
        if not procurement_data:
            self.db_manager.close()
            return self._create_error_result(record_id, "未找到采购数据")
        
        # 2. 处理附件文件 - 改进版本
        file_analysis = self._process_files_comprehensive(downloaded_files)
        
        # 3. 生成提示词并查询模型（使用model_engine中实际存在的方法）
        combined_content = file_analysis.get("combined_content", "")
        prompt = self.model_engine.generate_text_prompt(procurement_data, combined_content)
        model_response = self.model_engine.query_text_model(prompt)
        
        # 4. 解析结果（使用model_engine中实际存在的方法）
        if model_response:
            parsed_result = self.model_engine.parse_model_response(model_response)
        else:
            parsed_result = {"error": "模型查询失败"}
        
        # 5. 关闭数据库
        self.db_manager.close()
        
        # 6. 提取结构化信息
        structured_info = self._extract_structured_info(procurement_data, file_analysis)
        
        # 7. 返回结果
        result = {
            "record_id": record_id,
            "project_name": project_name,
            "search_keywords": parsed_result.get("search_keywords", []),
            "structured_info": structured_info,
            "file_analysis_summary": self._summarize_file_analysis(file_analysis),
            "status": "success" if parsed_result.get("search_keywords") else "failed",
            "error": parsed_result.get("error")
        }
        
        logger.info(f"记录处理完成 record_id={record_id}, status={result['status']}")
        return result
    
    def _process_files_comprehensive(self, file_paths):
        """综合处理文件列表"""
        analysis_result = {
            "text_files": [],
            "image_files": [],
            "structured_data": [],
            "combined_content": ""
        }
        
        text_contents = []
        
        for file_path in file_paths:
            file_info = self.file_processor.get_file_info(file_path)
            
            if not file_info['exists']:
                logger.warning(f"文件不存在: {file_path}")
                continue
            
            if self.file_processor.is_image_file(file_path):
                # 图片文件处理
                image_analysis = self._process_image_file(file_path)
                analysis_result["image_files"].append(image_analysis)
            else:
                # 文本文件处理
                text_content = self.file_processor.extract_text_from_file(file_path)
                if text_content and len(text_content.strip()) > 10:  # 确保有实际内容
                    text_contents.append(f"=== 文件: {file_info['path']} ===\n{text_content}")
                    
                    # 提取结构化数据
                    structured_data = self.file_processor.extract_file_structured_data(file_path)
                    analysis_result["structured_data"].append(structured_data)
                    
                    analysis_result["text_files"].append({
                        "path": file_info['path'],
                        "type": file_info['extension'],
                        "content_preview": text_content[:500] + "..." if len(text_content) > 500 else text_content,
                        "size_kb": round(file_info['size'] / 1024, 2)
                    })
        
        # 合并所有文本内容
        if text_contents:
            analysis_result["combined_content"] = "\n\n".join(text_contents)
        
        return analysis_result
    
    def _process_image_file(self, file_path):
        """处理图片文件"""
        try:
            logger.info(f"处理图片文件: {file_path}")
            # 使用图片文件的路径作为描述
            prompt = self.model_engine.generate_vision_prompt(f"分析图片文件：{file_path}")
            vision_response = self.model_engine.query_vision_model(prompt, file_path)
            
            if vision_response:
                return {
                    "path": file_path,
                    "analysis": vision_response,
                    "status": "success"
                }
            else:
                return {
                    "path": file_path,
                    "analysis": "图片分析失败",
                    "status": "failed"
                }
        except Exception as e:
            logger.error(f"图片处理失败 {file_path}: {e}")
            return {
                "path": file_path,
                "analysis": f"图片处理异常: {e}",
                "status": "error"
            }
    
    def _extract_structured_info(self, procurement_data, file_analysis):
        """提取结构化信息"""
        structured_info = {
            "commodities": [],
            "technical_requirements": [],
            "commercial_requirements": [],
            "brand_preferences": []
        }
        
        # 从采购数据提取
        if procurement_data.get('commodity_names'):
            for commodity in procurement_data['commodity_names']:
                if commodity:
                    structured_info["commodities"].append({
                        "name": commodity,
                        "type": "from_database"
                    })
        
        if procurement_data.get('suggested_brands'):
            for brand in procurement_data['suggested_brands']:
                if brand:
                    structured_info["brand_preferences"].append(brand)
        
        # 从文件内容提取关键信息
        combined_content = file_analysis.get("combined_content", "")
        if combined_content:
            # 提取技术参数
            tech_keywords = ['参数', '规格', '型号', '技术', '性能', '配置']
            for line in combined_content.split('\n'):
                if any(keyword in line for keyword in tech_keywords):
                    structured_info["technical_requirements"].append(line.strip())
            
            # 提取商业要求
            commercial_keywords = ['交付', '付款', '保修', '服务', '培训', '安装']
            for line in combined_content.split('\n'):
                if any(keyword in line for keyword in commercial_keywords):
                    structured_info["commercial_requirements"].append(line.strip())
        
        return structured_info
    
    def _summarize_file_analysis(self, file_analysis):
        """汇总文件分析结果"""
        return {
            "total_text_files": len(file_analysis.get("text_files", [])),
            "total_image_files": len(file_analysis.get("image_files", [])),
            "total_structured_data": len(file_analysis.get("structured_data", [])),
            "combined_content_length": len(file_analysis.get("combined_content", ""))
        }
    
    def _create_error_result(self, record_id, error_msg):
        """创建错误结果"""
        logger.error(f"处理失败 record_id={record_id}: {error_msg}")
        return {
            "record_id": record_id,
            "search_keywords": [],
            "structured_info": {},
            "status": "failed",
            "error": error_msg
        }
