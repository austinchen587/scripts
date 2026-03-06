# document_processor/ocr_processor.py

import os

# 再次确保环境变量设置，防止被其他模块覆盖
os.environ['NO_PROXY'] = 'localhost,127.0.0.1,0.0.0.0,::1'
os.environ['no_proxy'] = 'localhost,127.0.0.1,0.0.0.0,::1'






import ollama
from PIL import Image
import pytesseract
from pathlib import Path
import subprocess


def extract_from_image_with_ollama(image_path: Path, project_name: str) -> str:
    """使用 Ollama-VL 模型从图像提取采购需求"""
    prompt = (
        f"你是一位政府采购专家。请从这张技术参数表中提取商品采购需求。\n"
        f"项目名称：{project_name}\n\n"
        f"【提取要求】\n"
        f"1. 专注于提取商品技术参数和采购要求\n"
        f"2. 识别：商品名称、规格型号、技术参数、品牌要求、采购数量\n"
        f"3. 如果有表格，按行提取每个商品的信息\n"
        f"4. 忽略页眉页脚、公司信息等非技术内容\n"
        f"5. 输出格式：'商品名称: 规格型号要求; 数量: X台/套'\n\n"
        f"请开始提取："
    )
    try:
        # 使用二进制模式读取图片
        with open(image_path, "rb") as f:
            image_bytes = f.read()
            
        # 调用 Ollama (由于上方设置了 NO_PROXY，这里不会走代理)
        response = ollama.chat(
            model="qwen3-vl:4b",
            messages=[{"role": "user", "content": prompt, "images": [image_bytes]}],
            keep_alive=0  # <--- 核心修改：处理完图片立刻释放显存，退出模型
        )
        return response["message"]["content"].strip()
        
    except ollama.ResponseError as e:
        # 专门捕获 503 等 Ollama 服务端错误
        print(f"[OCR] ❌ Ollama 服务响应错误 (可能是代理问题): {e}")
        if "503" in str(e):
            print("[OCR] 💡 提示：请检查 config.py 中的 NO_PROXY 设置是否生效")
        return ""
    except Exception as e:
        print(f"[OCR] ❌ 图像分析失败 {image_path.name}: {e}")
        return ""

def extract_text_from_image_ocr(image_path: Path) -> str:
    """使用OCR提取图片文本（备用方案）"""
    try:
        image = Image.open(image_path)
        # 提高OCR准确性的预处理
        image = image.convert('L')  # 转为灰度
        
        # 尝试设置tesseract路径
        try:
            # 查找homebrew安装的tesseract路径 (MacOS) 或 Windows路径
            # 如果是Windows，通常需要手动指定，例如:
            # pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'
            pass
        except Exception:
            pass
        
        # 尝试多种语言配置
        try:
            # 先尝试中英文混合
            text = pytesseract.image_to_string(image, lang='chi_sim+eng')
            if text and len(text.strip()) > 10:  # 有足够文字
                return text.strip()
        except Exception as e1:
            # 静默失败，尝试下一级
            pass
        
        # 如果失败，只尝试英文
        try:
            text = pytesseract.image_to_string(image, lang='eng')
            if text:
                return text.strip()
        except Exception as e2:
            pass
        
        # 如果还失败，尝试无语言参数
        try:
            text = pytesseract.image_to_string(image)
            return text.strip()
        except Exception as e3:
            print(f"[OCR] ⚠️ 无语言OCR失败: {e3}")
            
        return ""
        
    except Exception as e:
        print(f"[OCR] ⚠️ OCR处理失败 {image_path.name}: {e}")
        return ""
