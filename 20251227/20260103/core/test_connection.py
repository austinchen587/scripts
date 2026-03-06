# test_connection.py
import ollama
import requests

def test_ollama_connection():
    print("=== Ollama连接测试 ===")
    
    # 方法1: 使用ollama库
    try:
        print("1. 测试ollama库...")
        models = ollama.list()
        print(f"✓ ollama库连接成功，找到 {len(models['models'])} 个模型")
        
        # 测试对话
        response = ollama.chat(
            model='qwen2.5:7b-instruct-q4_K_M',
            messages=[{'role': 'user', 'content': '简单回复"测试成功"'}]
        )
        print(f"✓ ollama对话成功: {response['message']['content']}")
    except Exception as e:
        print(f"✗ ollama库失败: {e}")
    
    # 方法2: 直接HTTP请求
    try:
        print("\n2. 测试HTTP连接...")
        response = requests.get("http://localhost:11434/api/tags", timeout=10)
        print(f"✓ HTTP连接成功: {response.status_code}")
        print(f"响应内容: {response.text[:200]}...")
    except Exception as e:
        print(f"✗ HTTP连接失败: {e}")
    
    # 方法3: 测试生成API
    try:
        print("\n3. 测试生成API...")
        data = {
            "model": "qwen2.5:7b-instruct-q4_K_M",
            "prompt": "简单回复测试成功",
            "stream": False
        }
        response = requests.post("http://localhost:11434/api/generate", json=data, timeout=30)
        print(f"✓ 生成API成功: {response.status_code}")
        if response.status_code == 200:
            result = response.json()
            print(f"响应: {result.get('response', '无响应')}")
    except Exception as e:
        print(f"✗ 生成API失败: {e}")

if __name__ == "__main__":
    test_ollama_connection()
