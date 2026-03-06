# D:\code\project\scripts\know_099\llm_client.py
import requests
import json
import re
from config import OLLAMA_URL, OLLAMA_MODEL, PROMPT_TEMPLATE

class OllamaClient:
    def __init__(self):
        self.headers = {"Content-Type": "application/json"}

    def extract_info(self, title):
        payload = {
            "model": OLLAMA_MODEL,
            "messages": [{"role": "user", "content": PROMPT_TEMPLATE.format(title=title)}],
            "format": "json",
            "stream": False,
            "options": {"temperature": 0.1, "num_ctx": 2048}
        }
        try:
            # === 修改点在这里 ===
            # 添加 proxies={"http": None, "https": None} 强制忽略系统代理
            resp = requests.post(
                OLLAMA_URL, 
                json=payload, 
                headers=self.headers, 
                timeout=30,
                proxies={"http": None, "https": None} 
            )
            
            if resp.status_code == 200:
                return self._parse_json(resp.json().get("message", {}).get("content", "{}"))
            return {}
        except Exception as e:
            # 这里打印错误更详细一点，方便确认是否还是代理问题
            print(f"LLM Call Error: {e}")
            return {}

    def _parse_json(self, content):
        try:
            return json.loads(content)
        except:
            # 简单的正则补救
            match = re.search(r'\{.*\}', content, re.DOTALL)
            return json.loads(match.group()) if match else {}