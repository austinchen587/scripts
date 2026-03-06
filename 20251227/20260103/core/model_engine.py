# model_engine.py
import ollama
import logging
from config import MODEL_CONFIG

logger = logging.getLogger(__name__)

class ModelEngine:
    def __init__(self):
        self.text_model = MODEL_CONFIG['text_model']
        self.vision_model = MODEL_CONFIG['vision_model']
        self.temperature = MODEL_CONFIG['temperature']
        self.max_tokens = MODEL_CONFIG['max_tokens']
    
    def generate_text_prompt(self, procurement_data, file_contents):
        """生成文本理解提示词"""
        prompt = f"""
        你是一个专业的采购商品关键词生成助手。请根据以下采购信息，生成适合在1688、淘宝、京东、拼多多等电商平台搜索的商品关键词。

        【采购基本信息】
        - 商品名称: {procurement_data.get('commodity_names', [])}
        - 参数要求: {procurement_data.get('parameter_requirements', [])}
        - 采购数量: {procurement_data.get('purchase_quantities', [])}
        - 控制金额: {procurement_data.get('control_amounts', [])}
        - 建议品牌: {procurement_data.get('suggested_brands', [])}
        - 商务条款: {procurement_data.get('business_items', [])}
        - 商务要求: {procurement_data.get('business_requirements', [])}

        【文件补充内容】
        {file_contents}

        【生成要求】
        1. 为每个商品生成3-5个最相关的商品搜索关键词
        2. 关键词要简洁明了，适合电商平台搜索
        3. 包含商品名字、品牌、型号等关键信息
        4. 用JSON格式返回，包含search_keywords字段
        5. 每个商品生成四个平台（1688、淘宝、京东、拼多多）的搜索关键词

        【具体指导】
        - 对于每个商品，尽量包含品牌、型号、规格、功能等信息
        - 如果有建议品牌，请明确列出
        - 如果有具体的参数要求，请将其转化为易于理解的关键词
        

        【返回格式】
        {{
            "search_keywords": [
                {{
                    "commodity_name": "商品1",
                    "platform_keywords": [
                        {{
                            "platform": "1688",
                            "keywords": ["关键词1", "关键词2", "关键词3"]
                        }},
                        {{
                            "platform": "淘宝",
                            "keywords": ["关键词1", "关键词2", "关键词3"]
                        }},
                        {{
                            "platform": "京东",
                            "keywords": ["关键词1", "关键词2", "关键词3"]
                        }},
                        {{
                            "platform": "拼多多",
                            "keywords": ["关键词1", "关键词2", "关键词3"]
                        }}
                    ]
                }},
                {{
                    "commodity_name": "商品2",
                    "platform_keywords": [
                        {{
                            "platform": "1688",
                            "keywords": ["关键词1", "关键词2", "关键词3"]
                        }},
                        {{
                            "platform": "淘宝",
                            "keywords": ["关键词1", "关键词2", "关键词3"]
                        }},
                        {{
                            "platform": "京东",
                            "keywords": ["关键词1", "关键词2", "关键词3"]
                        }},
                        {{
                            "platform": "拼多多",
                            "keywords": ["关键词1", "关键词2", "关键词3"]
                        }}
                    ]
                }},
                ...
            ],
            "reasoning": "生成理由说明"
        }}
        """
        return prompt
    
    def generate_vision_prompt(self, image_description):
        """生成视觉理解提示词"""
        prompt = f"""
        分析这张图片中的商品信息，生成适合电商搜索的关键词。
        
        图片描述: {image_description}
        
        请生成3-5个搜索关键词，用JSON格式返回。
        {{
            "search_keywords": ["关键词1", "关键词2", "关键词3"],
            "image_analysis": "图片分析结果"
        }}
        """
        return prompt
    
    def query_text_model(self, prompt):
        """查询文本模型"""
        try:
            response = ollama.chat(
                model=self.text_model,
                messages=[{"role": "user", "content": prompt}],
                options={
                    'temperature': self.temperature,
                    'num_predict': self.max_tokens
                }
            )
            logger.info("文本模型查询成功")
            return response['message']['content']
        except Exception as e:
            logger.error(f"文本模型查询失败: {e}")
            return None
    
    def query_vision_model(self, prompt, image_path):
        """查询视觉模型"""
        try:
            response = ollama.chat(
                model=self.vision_model,
                messages=[{"role": "user", "content": prompt, "images": [image_path]}],
                options={
                    'temperature': self.temperature,
                    'num_predict': self.max_tokens
                }
            )
            logger.info("视觉模型查询成功")
            return response['message']['content']
        except Exception as e:
            logger.error(f"视觉模型查询失败: {e}")
            return None
    
    def parse_model_response(self, response_text):
        """解析模型响应"""
        try:
            # 简单的JSON解析（实际使用时可以更复杂）
            if "search_keywords" in response_text:
                # 提取JSON部分
                import json
                import re
                
                # 尝试提取JSON
                json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
                if json_match:
                    return json.loads(json_match.group())
            
            # 如果解析失败，返回原始响应
            return {"raw_response": response_text}
        except Exception as e:
            logger.error(f"响应解析失败: {e}")
            return {"raw_response": response_text, "error": str(e)}
