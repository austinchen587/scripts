import requests
import re
import json
import logging
import time
from typing import Dict, Any, Optional
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
# ⚠️ [修改] 引入云端配置
from config import CLOUD_LLM_CONFIG 

logger = logging.getLogger(__name__)

class OllamaHandler:
    def __init__(self):
        # ⚠️ [修改] 切换为云端配置
        self.base_url = CLOUD_LLM_CONFIG["base_url"].strip().rstrip('/')
        # 🔧 确保 base_url 包含完整路径
        if not self.base_url.endswith('/chat/completions'):
            self.base_url = f"{self.base_url}/chat/completions"
            
        self.model = CLOUD_LLM_CONFIG["model"]
        self.api_key = CLOUD_LLM_CONFIG["api_key"]
        self.timeout = CLOUD_LLM_CONFIG["timeout"]
        # 🔧 缩短单次读取超时，让重试更快触发（避免 300×3=15分钟）
        self.single_timeout = min(self.timeout, 90)
        self.session = self._create_session()

    def _create_session(self):
        session = requests.Session()
        session.trust_env = False
        session.proxies = {"http": None, "https": None}
        
        # 🔧 配置 Retry：支持超时/连接错误/5xx 重试
        retry = Retry(
            total=3,  # ✅ 最大重试 3 次
            read=3,
            connect=3,
            backoff_factor=1.0,  # 指数退避: 1s, 2s, 4s
            status_forcelist=(429, 500, 502, 503, 504),  # ✅ 增加 429 速率限制
            allowed_methods=["POST", "GET"],  # ✅ 允许重试 POST
            raise_on_status=False,  # ✅ 关键：允许重试非 200 状态
            respect_retry_after_header=True,  # ✅ 尊重服务器的 Retry-After
        )
        adapter = HTTPAdapter(max_retries=retry)
        session.mount('http://', adapter)
        session.mount('https://', adapter)
        
        # ⚠️ [修改] 为云端 API 统一追加 Bearer Token 鉴权头
        session.headers.update({
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        })
        return session

    def check_connection(self) -> bool:
        # ⚠️ [修改] 云端接口无需 ping tags，直接校验 key 格式即可
        if not self.api_key or "sk-" not in self.api_key:
            logger.error("❌ 尚未配置有效的 API Key！")
            return False
        return True

    def clean_text_artifacts(self, text: str) -> str:
        """清洗 Python 列表残留符号及花括号"""
        if not text: return ""
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
            "苗", "树", "被", "枕", "床", "油", "米", "面", "粮"
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

    def call_model(self, prompt: str, max_retries: int = 3) -> Optional[str]:
        """调用云端模型 - 支持重试 + 关闭思考"""
        
        # 🔧 构建 payload：enable_thinking 直接放顶层（阿里云兼容接口规范）
        data = {
            "model": self.model, 
            "messages": [
                {"role": "system", "content": "你是一个输出标准化JSON的机器。"},
                {"role": "user", "content": prompt}
            ],
            "temperature": CLOUD_LLM_CONFIG.get("temperature", 0.1),
            "response_format": {"type": "json_object"},
            # ✅ 关键：关闭思考功能 - 直接放顶层！
            "enable_thinking": False,
        }
        
        # 🔁 手动重试循环（比 urllib3.Retry 更可控）
        last_error = None
        for attempt in range(1, max_retries + 1):
            try:
                print(f"\n  [API 连线] 尝试 {attempt}/{max_retries} 呼叫 {self.model} ...")
                print(f"  [API 配置] 单次超时: {self.single_timeout}s | 🧠思考: 关闭")
                
                start_time = time.time()
                
                # 🔧 使用缩短后的单次超时
                response = self.session.post(
                    self.base_url, 
                    json=data, 
                    timeout=(10, self.single_timeout),  # (connect, read)
                    headers=self.session.headers
                )
                
                elapsed = time.time() - start_time
                print(f"  [API 响应] 状态码: {response.status_code} | 耗时: {elapsed:.2f}s")
                
                # 🔧 处理 429 速率限制
                if response.status_code == 429:
                    retry_after = int(response.headers.get("Retry-After", 5))
                    print(f"  [API 限流] 等待 {retry_after}秒后重试...")
                    time.sleep(retry_after)
                    continue
                
                response.raise_for_status()
                
                result_text = response.json()["choices"][0]["message"]["content"].strip()
                print(f"  [API 返回] 内容: {result_text[:200]}{'...' if len(result_text) > 200 else ''}")
                return result_text
                
            except requests.exceptions.ReadTimeout:
                last_error = f"读取超时 ({self.single_timeout}s)"
                print(f"\n❌ 警告: 云端API读取超时！{last_error}")
                
            except requests.exceptions.ConnectTimeout:
                last_error = "连接超时"
                print(f"\n❌ 警告: 云端API连接超时！{last_error}")
                
            except requests.exceptions.ConnectionError as e:
                last_error = f"连接错误: {e}"
                print(f"\n❌ 警告: 网络连接失败！{last_error}")
                
            except requests.exceptions.HTTPError as e:
                status = e.response.status_code if hasattr(e, 'response') else '未知'
                last_error = f"HTTP {status} 错误"
                print(f"\n❌ 警告: API 返回 {last_error}")
                if hasattr(e, 'response') and e.response.text:
                    try:
                        err = e.response.json()
                        print(f"  [错误详情] {err.get('error', {}).get('message', e.response.text[:100])}")
                    except:
                        print(f"  [错误详情] {e.response.text[:100]}")
                # 5xx 错误可重试，4xx 通常不可重试
                if status < 500:
                    break
                    
            except json.JSONDecodeError as e:
                print(f"\n❌ 错误: 响应解析失败 - {e}")
                print(f"  [原始响应] {response.text[:200] if 'response' in locals() else 'N/A'}")
                return None  # 解析错误通常不需要重试
                
            except Exception as e:
                last_error = f"{type(e).__name__}: {e}"
                print(f"\n❌ 错误: 调用异常 - {last_error}")
                logger.error(f"调用云端模型出错: {last_error}")
                # 未知错误不重试，直接返回
                return None
            
            # 🔁 指数退避等待后重试
            if attempt < max_retries:
                wait_time = 2 ** (attempt - 1)  # 1s, 2s, 4s
                print(f"  [重试策略] {wait_time}秒后第 {attempt+1} 次尝试...")
                time.sleep(wait_time)
        
        # 🔥 所有重试失败
        print(f"\n💥 重试耗尽 ({max_retries}次)，最后错误: {last_error}")
        with open("llm_api_error.log", "a", encoding="utf-8") as f:
            f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} - 重试失败: {last_error}\n")
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
        
        # ⚠️ [终极进化版] 完美融合：反向SEO极简法则 + 核心参数强制提取思维链
        prompt = f"""你是一个深谙淘宝、京东、1688底层搜索逻辑且具备极强专业采购背景的顶级电商买手。
你的任务是将长篇大论的"政企采购需求"，精准翻译成能搜出【完全符合硬性参数要求】的电商搜索词。

【原始采购数据】
商品名称：{item_name}
参考品牌：{suggested_brand if suggested_brand else '无'}
规格描述：{self.clean_specifications(specifications)[:400]}
采购数量：{quantity if quantity else '未知'}

【🚨 核心参数提取与反向 SEO 法则（生死红线）】
1. **精准抓取决定性参数**：你必须从规格中揪出那些【决定设备分类、大小、原理、价格量级】的核心物理参数！（如：118mm/热转印、i7/16G）。
2. **纠正名词偏差**：如果需求写着"票据打印机"，但规格要求"118mm宽幅、热转印、装碳带"，你必须懂行，知道这在电商上叫"热转印标签打印机"！
3. **只要骨干，拒绝赘肉**：电商搜索引擎极其愚蠢！最终搜索词**最多包含3-4个核心词汇**（修正后的名词 + 核心参数）。
4. **绝对禁止的词汇**：
   - 严禁出现任何包装数量（如：500张/包、4包/箱、10卷/提）。
   - 严禁出现极其详细的琐碎尺寸（如：297*420mm -> 必须转换为电商通用词A3）。
   - 严禁出现描述性废话（如：带检测报告、双面、不透明、加厚、预算控制、必须正品）。

【平台智能路由法则】
- 【京东】：数码电器、办公高价值设备、对参数要求极度严格的工业品。必须精确包含核心参数！
- 【1688】：当采购数量巨大（>100）且带有明显定制属性或工业耗材批发时，必须选1688。
- 【淘宝】：日杂百货、五金劳保、零碎耗材。

【翻译实战案例】
[输入]: 针式打印机 进纸宽度≥118mm 热敏/热转印 碳带装载量≥300m
[思考]: 宽幅118+热转印+碳带，这是典型的工业桌面标签打印机。不能只搜"票据打印机"否则全是58mm外卖机。
[输出]: {{"core_params": "118mm 热转印", "keyword": "热转印标签打印机 118mm", "platform": "京东"}}

[输入]: A3多功能复印纸（A3 80g 双面复印纸500张/包、4包/箱 297*420mm）
[思考]: A3和80g是核心参数，500张是废话，297*420mm需转为A3。
[输出]: {{"core_params": "A3 80g", "keyword": "A3复印纸 80g", "platform": "京东"}}

请基于以上法则，严格输出JSON格式：
{{
    "core_params": "你提取的决定性核心参数（不超过3个词）",
    "keyword": "最精简、最精准的电商搜索词",
    "platform": "京东/淘宝/1688"
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