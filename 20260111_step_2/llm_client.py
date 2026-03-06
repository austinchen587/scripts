# llm_client.py - 增强版
import requests
import json
import time
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from config import OLLAMA_URL, LLM_MODEL

def create_retry_session(retries=3, backoff_factor=0.5, status_forcelist=(500, 502, 504)):
    """创建带重试机制的session"""
    session = requests.Session()
    retry = Retry(
        total=retries,
        read=retries,
        connect=retries,
        backoff_factor=backoff_factor,
        status_forcelist=status_forcelist,
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount('http://', adapter)
    session.mount('https://', adapter)
    return session

def call_qwen3(prompt: str) -> str:
    """调用Qwen-3模型，包含超时和重试机制"""
    payload = {
        "model": LLM_MODEL,
        "prompt": prompt,
        "stream": False,
        "keep_alive": 0,  # <--- 核心修改：强制处理完后立即从显存中退出卸载
        "options": {
            "temperature": 0.1,
            "num_predict": 8192,   # 允许输出更长
            "num_ctx": 12288,      # 提高到12K窗口，Qwen-8B在8G显存下通常能撑住
            "top_p": 0.9           # 增加一点稳定性
        }
    }
    
    # 智能超时策略
    prompt_length = len(prompt)
    
    # 超时基准（秒）
    base_timeout = 300  # 5分钟
    
    # 根据提示词长度调整
    if prompt_length > 8000:  # 非常长的提示词
        timeout = 600  # 10分钟
    elif prompt_length > 4000:  # 长提示词
        timeout = 450  # 7.5分钟
    else:  # 正常长度
        timeout = base_timeout
    
    print(f"[LLM] ⏱️ 提示词长度: {prompt_length} 字符，设置超时: {timeout}秒")
    
    try:
        # 创建带重试的session - 【关键修改】
        session = create_retry_session(retries=2)
        
        # 【关键修复】添加这两行，绕过代理
        session.trust_env = False  # 不信任环境变量中的代理
        session.proxies = {}       # 明确设置空代理
        
        # 设置更详细的超时参数
        timeout_params = (10, timeout)  # (连接超时, 读取超时)
        
        # 添加详细的调试信息
        print(f"[LLM] 🚀 开始调用LLM (模型: {LLM_MODEL}, URL: {OLLAMA_URL})")
        start_time = time.time()
        
        resp = session.post(
            OLLAMA_URL, 
            json=payload, 
            timeout=timeout_params,
            headers={'Content-Type': 'application/json'},
            verify=False  # 如果是自签名证书
        )
        
        elapsed = time.time() - start_time
        print(f"[LLM] ✅ LLM调用成功，耗时: {elapsed:.1f}秒")
        
        resp.raise_for_status()
        
        # 解析响应
        response_json = resp.json()
        response_text = response_json.get("response", "").strip()
        
        if not response_text:
            print("[LLM] ⚠️ LLM返回了空响应")
            return ""
        
        print(f"[LLM] 📨 收到响应: {len(response_text)} 字符")
        if len(response_text) > 500:
            print(f"[LLM] 📄 响应预览: {response_text[:300]}...")
        
        return response_text
        
    except requests.exceptions.Timeout as e:
        print(f"🤖 LLM 调用超时 ({timeout}秒): {e}")
        # 记录问题到日志文件
        with open("llm_timeout.log", "a", encoding="utf-8") as f:
            f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} | 超时: {timeout}s | 提示词长度: {prompt_length}\n")
        return ""
    except requests.exceptions.RequestException as e:
        print(f"🤖 LLM 网络错误: {e}")
        return ""
    except Exception as e:
        print(f"🤖 LLM 未知错误: {type(e).__name__}: {e}")
        return ""
