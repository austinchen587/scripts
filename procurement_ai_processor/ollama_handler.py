import requests
import re
import json
import logging
from typing import Dict, Any, Optional
from config import OLLAMA_CONFIG

logger = logging.getLogger(__name__)

class OllamaHandler:
    def __init__(self):
        self.base_url = OLLAMA_CONFIG["base_url"]
        self.model = OLLAMA_CONFIG["model"]
        self.timeout = OLLAMA_CONFIG["timeout"]
        self.session = self._create_session()

    def _create_session(self):
        session = requests.Session()
        session.trust_env = False
        session.proxies = {"http": None, "https": None}
        return session

    def check_connection(self) -> bool:
        try:
            test_url = f"{self.base_url}/api/tags"
            response = self.session.get(test_url, timeout=5)
            return response.status_code == 200
        except Exception as e:
            logger.error(f"无法连接到Ollama服务: {e}")
            return False

    def clean_text_artifacts(self, text: str) -> str:
        """清洗 Python 列表残留符号及花括号"""
        if not text: return ""
        # [修改] 同时移除 [] {} 和引号
        cleaned = re.sub(r"[\[\]\{\}'\"']", "", str(text))
        return cleaned.strip()

    def clean_specifications(self, spec_text: str) -> str:
        """清洗冗余规格描述"""
        if not spec_text: return ""
        spec_text = self.clean_text_artifacts(spec_text)
        cleaned = re.sub(r'核心参数要求:商品类目:[^;]*;?', '', spec_text)
        cleaned = re.sub(r'次要参数要求:?', '', cleaned)
        cleaned = re.sub(r'\s+', ' ', cleaned)
        cleaned = cleaned.strip()
        cleaned = re.sub(r'^[，。、;；:]|[，。、;；:]$', '', cleaned)
        return cleaned.strip()
    
    def is_product_type(self, item_name: str) -> bool:
        """判断是否为商品（白名单+黑名单机制）"""
        if not item_name: return True
        item_clean = str(item_name).strip()
        
        whitelist = [
            "设备", "材料", "管", "泵", "阀", "灯", "柜", "架", 
            "器", "机", "仪", "表", "电池", "车", "电脑", "纸", "本",
            "互感器", "变压器", "耗材", "硬盘", "内存", "家具", "桌", "椅",
            "苗", "树", "被", "枕", "床", "油", "米", "面", "粮" # [新增] 粮油白名单
        ]
        for white_word in whitelist:
            if white_word in item_clean: return True
        
        non_product_keywords = ["服务", "运维", "咨询", "培训", "租赁", "维修", "劳务", "检测", "设计", "施工"]
        for keyword in non_product_keywords:
            if re.search(rf'{re.escape(keyword)}(?:\b|$)', item_clean):
                return False
        return True
    
    def generate_commodity_summary(self, item_name: str, specifications: str) -> str:
        if not item_name: return ""
        clean_spec = self.clean_specifications(specifications)
        if not clean_spec: return item_name
        if len(clean_spec) > 100: clean_spec = clean_spec[:100] + "..."
        return f"{item_name}（{clean_spec}）"

    def parse_json_response(self, text: str) -> Dict[str, str]:
        """解析模型返回的 JSON"""
        try:
            match = re.search(r'```json\s*(.*?)\s*```', text, re.DOTALL)
            if match:
                json_str = match.group(1)
            else:
                match = re.search(r'\{.*\}', text, re.DOTALL)
                json_str = match.group(0) if match else text

            data = json.loads(json_str)
            return {
                "keyword": data.get("keyword", ""),
                "platform": data.get("platform", "其他")
            }
        except Exception:
            return {"keyword": text[:25], "platform": "未知"}

    def call_model(self, prompt: str) -> Optional[str]:
        try:
            url = f"{self.base_url}/api/generate"
            data = {
                "model": self.model, 
                "prompt": prompt, 
                "stream": False, 
                # "format": "json", # ⚠️ [修改点1] 注释掉强制JSON格式，防止新模型不兼容报错
                "options": {
                    "temperature": 0.1,
                    "num_predict": 256  # ⚠️ [修改点2] 稍微放大输出长度，防止截断
                }
            }
            response = self.session.post(url, json=data, timeout=self.timeout)
            
            if response.status_code == 200:
                return response.json().get("response", "").strip()
            else:
                # ⚠️ [修改点3] 把 Ollama 真实的报错原因打印到控制台！
                print(f"\n❌ 警告: Ollama 拒绝了请求! 状态码: {response.status_code}, 详情: {response.text}")
                return None
                
        except requests.exceptions.ReadTimeout:
            print("\n❌ 警告: Ollama 处理超时！(可能模型加载太慢)")
            return None
        except Exception as e:
            logger.error(f"调用Ollama出错: {e}")
            return None
    def process_commodity(self, item_name: str, suggested_brand: str = "", specifications: str = "", quantity: Any = None) -> Dict[str, Any]:
        """主处理逻辑"""
        result = {
            "is_product": True,
            "processed": False,
            "key_word": "",
            "search_platform": "",
            "commodity_summary": ""
        }
        
        item_name = self.clean_text_artifacts(item_name)
        suggested_brand = self.clean_text_artifacts(suggested_brand)
        
        if not self.is_product_type(item_name):
            result["is_product"] = False
            result["commodity_summary"] = item_name
            return result
        
        commodity_summary = self.generate_commodity_summary(item_name, specifications)
        result["commodity_summary"] = commodity_summary
        
        if not self.check_connection():
            result["key_word"] = commodity_summary
            result["search_platform"] = "本地解析"
            return result
        
        # --- 核心 Prompt 优化 (去数量化 + 多品牌分割 + 强化京东淘宝) ---
        prompt = f"""你是一个高级采购专家。请分析商品数据：
商品名称：{item_name}
参考品牌：{suggested_brand if suggested_brand else '无'}
规格描述：{self.clean_specifications(specifications)[:200]}
采购数量：{quantity if quantity else '未知'}

请完成以下任务并输出JSON：

1. **提取搜索词 (keyword)**：
   - **【禁止数量】**：**绝对不允许**在关键词中出现采购数量词（如“50个”、“3件套”、“20卷”、“批”等）！
   - **【基本格式】**：品牌(如有) + 商品名 + 核心配置/规格。若无品牌限制，仅输出商品名+规格。
   - **【多品牌特殊规则】**：如果“参考品牌”包含多个品牌选项（如包含'/'、'、'等符号，例如“德力西/公牛/正泰”），请为**每个品牌分别生成**一个独立的搜索词，并**必须使用双竖线 `||` 将它们拼接起来**。示例：`德力西电工胶布||公牛电工胶布||正泰电工胶布`。
   - **【电脑类强制规则】**：若商品是台式机/笔记本/服务器，**必须包含** CPU型号、内存大小(如16G) 和 硬盘大小(如512G)。
   - **【简写节省字数】**：
     - '16GB' -> '16G'
     - '512GB SSD' -> '512G'
     - '集成显卡' -> (直接省略)
     - '台式计算机' -> '台式机'
   - **长度控制**：单个关键词（电脑类）允许 **35字**，其他商品保持 **20字**，去除形容词。
   - **防串扰**：严格基于本次提供的规格描述提取，**绝对不要**使用常识或其他商品的规格。
   - **冲突修正**：若商品名与规格矛盾，以规格为准。

2. **推荐平台 (platform)**（仅在京东、淘宝、1688中选择）：
   - **核心基调**：主要以 **京东** 和 **淘宝** 为主。尽量减少1688的推荐。
   - **京东**：电脑数码、标准电器、图书、办公耗材及设备、高价值商品、急需现货（侧重正品与时效）。
   - **淘宝**：日用消耗品（清洁剂、垃圾袋等）、非标品、五金零配件（水龙头/插销/合页/螺丝刀等）、冷门长尾商品、装饰品、农资苗木（侧重品类丰富与性价比）。
   - **1688**：需要源头定制加工（如刻章、大型工业阀门）时才推荐。

输出示例（多品牌情况）：
{{
    "keyword": "德力西定时开关||公牛定时开关||正泰定时开关",
    "platform": "淘宝"
}}

输出示例（单品牌或无品牌情况）：
{{
    "keyword": "联想台式机i5-13400 16G 512G",
    "platform": "京东"
}}
"""
        ai_response = self.call_model(prompt)
        
        if ai_response:
            parsed = self.parse_json_response(ai_response)
            result["key_word"] = parsed["keyword"]
            result["search_platform"] = parsed["platform"]
            result["processed"] = True
        else:
            result["key_word"] = commodity_summary
            result["search_platform"] = "AI调用失败"
        
        return result