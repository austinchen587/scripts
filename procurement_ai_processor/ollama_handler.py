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
        
        # --- 核心 Prompt 优化 (去数量化 + 多品牌分割 + 强化京东淘宝 + 实战错题本 + 主语防丢补丁) ---
        prompt = f"""你是一个高级电商采购搜索专家。请分析商品数据：
商品名称：{item_name}
参考品牌：{suggested_brand if suggested_brand else '无'}
规格描述：{self.clean_specifications(specifications)[:200]}
采购数量：{quantity if quantity else '未知'}

请完成以下任务并输出JSON：

1. **提取搜索词 (keyword)**：
   - **【禁止数量与无用词】**：**绝对不允许**出现数量词（如“30个”、“3件”、“50盒”、“1080支”）。禁止出现“白色”、“安全门锁”、“以上”等长串修饰语。
   - **【基本格式】**：中文品牌(如有) + 商品名 + 核心型号/规格。
   - **【多品牌与中英文过滤】**：如果包含多个品牌（如“联想/lenovo华为/huawei”或“得力/deli晨光/m&g”），**只保留纯中文品牌名**，并为**每个品牌分别生成**独立搜索词，必须用双竖线 `||` 拼接。示例：`联想 笔记本||华为 笔记本`。**绝对不要在最终结果里保留 `/` 符号**。
   - **【电脑类强制规则】**：“便携式计算机”必须转换成“笔记本”。必须包含 CPU、内存、硬盘。简写形式：16GB->16G，1TB SSD->1T。
   - **【核心主语强制保留】（极其重要）**：无论规格多么详细，**最终的搜索词中必须包含原本的“商品名称”**！绝对不允许只提炼规格而把商品本身的名字弄丢。
   - **防串扰**：若商品名与规格矛盾，以规格为准。

2. **推荐平台 (platform)**（仅在京东、淘宝、1688中选择）：
   - **京东**：电脑数码、标准电器（冷柜等）、图书、办公耗材及设备（打印机/硒鼓/中性笔/复印纸）。
   - **淘宝**：日用消耗品（垃圾袋/指甲剪/马桶刷）、五金零配件（胶水/胶条）、体育及手工材料（实验耗材/漆包线）、冷门长尾商品。
   - **1688**：仅限源头定制、大型工业材料。

【极其重要的输出示例】（请严格模仿以下案例的思维生成 keyword）：

示例 1：过滤多品牌英文别名 + 计算机术语转换（必须用||分割）！
输入 -> 商品名称: 便携式计算机, 规格描述: 内存32;CPU:Ultra 9;硬盘:1T SSD;颜色:灰, 参考品牌: 联想/lenovo华为/huawei
生成 -> "keyword": "联想 笔记本 Ultra9 32G 1T||华为 笔记本 Ultra9 32G 1T"
（错误示范：联想/lenovo便携式计算机... —— 绝对不能保留英文和斜杠！）

示例 2：文具类多品牌完美分割 + 过滤数量！
输入 -> 商品名称: 黑笔(中性笔), 规格描述: 晨光/得力 0.5mm, 采购数量: 1080支, 参考品牌: 得力/deli晨光/m&g
生成 -> "keyword": "得力 0.5mm 中性笔||晨光 0.5mm 中性笔"
（错误示范：得力/晨光0.5mm中性笔 —— 绝对不能保留斜杠，必须用||切开！）

示例 3：强力过滤纯数字与数量词！
输入 -> 商品名称: 透明盛液筒, 规格描述: 无, 采购数量: 30个, 参考品牌: 无
生成 -> "keyword": "透明盛液筒"
（错误示范：透明盛液筒30个 —— 绝对不能带任何数量！）

示例 4：过滤电商废话属性，提取核心！
输入 -> 商品名称: 冰柜, 规格描述: 白色;有效容积:≥200L;立式;安全门锁, 参考品牌: 海尔/Haier美的星星澳柯玛/aucma
生成 -> "keyword": "海尔 立式冰柜 200L||美的 立式冰柜 200L||星星 立式冰柜 200L||澳柯玛 立式冰柜 200L"

示例 5：主语强制保留防丢失！
输入 -> 商品名称: 马桶刷, 规格描述: 长柄圆刷, 采购数量: 10个, 参考品牌: 无
生成 -> "keyword": "马桶刷 长柄圆刷"
（错误示范：长柄圆刷 —— 绝对不能丢掉真正的商品名“马桶刷”！）

请最终输出合法的JSON格式：
{{
    "keyword": "提取出的搜索词",
    "platform": "推荐的平台"
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