import sys
import requests
import json
import time
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from config import OLLAMA_URL, LLM_MODEL, CLOUD_LLM_CONFIG


def create_retry_session(retries=3, backoff_factor=1.0, status_forcelist=(500, 502, 504)):
    """创建带重试机制的session - 支持超时/连接错误重试"""
    session = requests.Session()
    retry = Retry(
        total=retries,
        read=retries,
        connect=retries,
        backoff_factor=backoff_factor,  # 指数退避: 1s, 2s, 4s
        status_forcelist=status_forcelist,
        allowed_methods=["POST", "GET"],  # ✅ 允许重试 POST 请求
        raise_on_status=False,  # ✅ 关键：允许重试非 200 状态码
        respect_retry_after_header=True,  # ✅ 尊重服务器的 Retry-After 头
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount('http://', adapter)
    session.mount('https://', adapter)
    return session


def call_qwen3(prompt: str) -> str:
    """调用云端 Qwen 模型 - 关闭思考 + 超时重试"""
    session = create_retry_session()
    
    # 🔧 缩短单次读取超时，让重试更快触发（避免 300×3=15分钟等待）
    timeout = min(CLOUD_LLM_CONFIG.get("timeout", 300), 90)
    timeout_params = (10, timeout)  # (连接超时, 读取超时)
    
    # 🔧 修复 base_url：去掉末尾空格 + 确保路径正确
    base_url = CLOUD_LLM_CONFIG['base_url'].strip().rstrip('/')
    api_url = f"{base_url}/chat/completions" if not base_url.endswith('/chat/completions') else base_url
    
    # 构建请求头
    headers = {
        "Authorization": f"Bearer {CLOUD_LLM_CONFIG['api_key']}",
        "Content-Type": "application/json"
    }
    
    # 🔧 关键修复：enable_thinking 直接放 payload 顶层（阿里云兼容接口规范）
    payload = {
        "model": CLOUD_LLM_CONFIG["model"],
        "messages": [{"role": "user", "content": prompt}],
        "temperature": CLOUD_LLM_CONFIG["temperature"],
        "enable_thinking": False,  # ✅ 关闭思考功能 - 直接放顶层！
    }
    
    print(f"\n" + "-"*40)
    print(f"| 🌐 [云端API请求] 准备调用...")
    print(f"| 📦 目标模型: {CLOUD_LLM_CONFIG.get('model', '未知模型')}")
    print(f"| 🔗 接口地址: {api_url}")
    print(f"| 🧠 思考功能: 关闭")
    print(f"| ⏱️ 单次超时: {timeout}秒 | 🔄 最大重试: 3次")
    print(f"| 📝 提示词长度: {len(prompt)} 字符")
    print("-" * 40)
    sys.stdout.flush()
    
    start_time = time.time()
    
    try:
        resp = session.post(
            api_url, 
            json=payload, 
            timeout=timeout_params,
            headers=headers
        )
        
        elapsed = time.time() - start_time
        resp.raise_for_status()
        
        response_json = resp.json()
        request_id = response_json.get("id", response_json.get("request_id", "未知ID"))
        response_text = response_json.get("choices", [{}])[0].get("message", {}).get("content", "").strip()
        
        print(f"| ✅ [云端API响应] 成功！耗时: {elapsed:.2f}秒")
        print(f"| 🔖 Request ID: {request_id}")
        
        if not response_text:
            print("| ⚠️ [云端API响应] 警告：模型返回了空文本！")
            print("-" * 40 + "\n")
            sys.stdout.flush()
            return ""
        
        print(f"| 📨 收到字符数: {len(response_text)}")
        print(f"| 📄 响应预览: {response_text[:100]}...")
        print("-" * 40 + "\n")
        sys.stdout.flush()
        
        return response_text
        
    except requests.exceptions.Timeout as e:
        elapsed = time.time() - start_time
        print(f"| ❌ [云端API报错] 请求超时！(已等待 {elapsed:.1f}秒)")
        print(f"| 💡 提示：已配置自动重试，若仍失败请检查网络或模型名称")
        print(f"| 详情: {e}")
        print("-" * 40 + "\n")
        sys.stdout.flush()
        with open("llm_timeout.log", "a", encoding="utf-8") as f:
            f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} - 超时: {str(e)}\n")
        return ""
        
    except requests.exceptions.ConnectionError as e:
        elapsed = time.time() - start_time
        print(f"| ❌ [云端API报错] 连接失败！(已等待 {elapsed:.1f}秒)")
        print(f"| 💡 提示：检查网络或防火墙，已配置自动重试")
        print(f"| 详情: {e}")
        print("-" * 40 + "\n")
        sys.stdout.flush()
        return ""
        
    except requests.exceptions.HTTPError as e:
        # 处理 4xx/5xx 错误
        elapsed = time.time() - start_time
        status_code = e.response.status_code if hasattr(e, 'response') else '未知'
        print(f"| ❌ [云端API报错] HTTP {status_code} 错误！(已等待 {elapsed:.1f}秒)")
        
        if hasattr(e, 'response') and e.response.text:
            try:
                err_json = e.response.json()
                print(f"| 📋 错误详情: {err_json.get('error', {}).get('message', e.response.text[:200])}")
            except:
                print(f"| 📋 错误详情: {e.response.text[:200]}")
        
        print("-" * 40 + "\n")
        sys.stdout.flush()
        return ""
        
    except Exception as e:
        print(f"| ❌ [云端API报错] 调用异常: {type(e).__name__}")
        print(f"| 详情: {e}")
        if 'resp' in locals() and hasattr(resp, 'text'):
            req_id = resp.headers.get("X-Request-Id", "未知ID")
            print(f"| 🔖 Request ID: {req_id}")
            print(f"| 服务器返回: {resp.text[:200]}")
        print("-" * 40 + "\n")
        sys.stdout.flush()
        return ""