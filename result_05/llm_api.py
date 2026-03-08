import requests
import json
import time
from config import OLLAMA_CONFIG, BATCH_CONFIG
import base64
import os


def build_batch_prompt(demand, batch_candidates):
    """构建海选 Prompt"""
    simple_list = []
    for c in batch_candidates:
        simple_list.append({
            "sku": c.get('sku'),
            "title": c.get('title', '')[:40],
            "price": c.get('price'),
            "sales": c.get('sales'),
            "shop": c.get('shop_name', '')[:8],
            "info": c.get('hot_info', '')[:10]
        })
    return f"""
    作为采购专家，请从这{len(simple_list)}家候选中筛选{BATCH_CONFIG['winners_per_batch']}家晋级。
    【需求】{demand.get('item_name')}
    【规则】1.符合需求(最重要) 2.价格低 3.销量高
    【列表】
    {json.dumps(simple_list, ensure_ascii=False)}
    请严格输出JSON: {{"winners": [{{"sku": "...", "reason": "..."}}]}}
    """

def build_final_prompt(demand, finalists):
    """构建决赛 Prompt"""
    simple_list = []
    for c in finalists:
        simple_list.append({
            "sku": c.get('sku'),
            "title": c.get('title', ''), 
            "price": c.get('price'), 
            "sales": c.get('sales'),
            "shop": c.get('shop_name'),
            # 👉 [修改] 这里改为读取处理后的最终参数
            "real_specs": c.get('final_specs_text', '无真实参数') 
        })
    
    return f"""
    【终极决选】从这{len(finalists)}家优胜者中选出最终3家。
    
    【需求】{demand.get('item_name')}
    【硬性规则】：
    1. 必须完全符合需求规格。
    2. 🚨【重点防骗】：请你务必阅读下方列表中提供的 'real_specs(真实参数)'，如果参数中写明是“配件”、“外壳”或者“尺寸与需求不符”，你必须直接将其淘汰！
    3. 在参数正确的前提下，价格最低优先，参考销量评价。
    
    【候选列表】
    {json.dumps(simple_list, ensure_ascii=False)}
    
    请输出JSON:
    {{
        "selected": [
            {{"rank": 1, "sku": "...", "reason": "核对真实参数发现...,且价格..."}},
            {{"rank": 2, "sku": "...", "reason": "..."}},
            {{"rank": 3, "sku": "...", "reason": "..."}}
        ],
        "overall_reasoning": "总结"
    }}
    """

def invoke_ollama(prompt, desc=""):
    """底层API调用，含重试"""
    url = f"{OLLAMA_CONFIG['base_url']}/api/chat"
    payload = {
        "model": OLLAMA_CONFIG['model'],
        "messages": [{"role": "user", "content": prompt}],
        "format": "json", "stream": False
    }
    for attempt in range(3):
        try:
            resp = requests.post(url, json=payload, timeout=OLLAMA_CONFIG['timeout'])
            resp.raise_for_status()
            return json.loads(resp.json()['message']['content'])
        except Exception as e:
            if attempt == 2: print(f"    ! {desc} 失败: {e}")
            time.sleep(BATCH_CONFIG['retry_backoff'])
    return None

# ============================================================
# 👉 [新增] 召唤 Qwen-VL 视觉大模型
# ============================================================
def analyze_image_with_vl(image_path, item_name):
    """调用本地 qwen3-vl:4b 识别商品详情图"""
    if not image_path or not os.path.exists(image_path):
        return "本地图片文件不存在"

    try:
        # 将本地截图转换为 Base64 编码
        with open(image_path, "rb") as f:
            base64_image = base64.b64encode(f.read()).decode('utf-8')
    except Exception as e:
        return f"读取图片失败: {e}"

    url = f"{OLLAMA_CONFIG['base_url']}/api/chat"
    # 给视觉模型下达指令
    prompt = f"这是一张电商商品【{item_name}】的详情截图。请帮我提取图片中的核心规格参数（例如：型号、尺寸、材质、容量等）。请直接用清晰的文本返回你看到的参数，绝不要编造图片里没有的内容。"

    payload = {
        "model": "qwen3-vl:4b",  # 使用你刚下载的视觉模型
        "messages": [
            {
                "role": "user",
                "content": prompt,
                "images": [base64_image] # Ollama 原生支持直接传图
            }
        ],
        "stream": False
    }

    try:
        resp = requests.post(url, json=payload, timeout=120)
        resp.raise_for_status()
        return resp.json()['message']['content']
    except Exception as e:
        return f"视觉解析失败: {e}"
