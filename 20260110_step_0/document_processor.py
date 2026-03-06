import subprocess
import time
from pathlib import Path
import pdfplumber
from pdf2image import convert_from_path
import ollama
from config import PDF_DIR, IMG_DIR, LIBREOFFICE_PATH, POPPLER_BIN_PATH, OLLAMA_VL_MODEL

_OLLAMA_VL_FIRST_CALL = True

def log_info(msg): print(f"    ℹ️  {msg}")
def log_success(msg): print(f"    ✅ {msg}")
def log_warning(msg): print(f"    ⚠️  {msg}")
def log_error(msg): print(f"    ❌ {msg}")

def office_to_pdf(input_path: Path) -> Path:
    output_pdf = PDF_DIR / f"{input_path.stem}.pdf"
    if output_pdf.exists():
        return output_pdf
    cmd = [
        LIBREOFFICE_PATH,
        "--headless",
        "--convert-to", "pdf",
        "--outdir", str(PDF_DIR),
        str(input_path)
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    if result.returncode != 0 or not output_pdf.exists():
        raise RuntimeError(f"LibreOffice 转换失败: {result.stderr}")
    return output_pdf

def extract_text_from_pdf_native(pdf_path: Path) -> str:
    log_info(f"尝试原生提取 PDF 文字: {pdf_path.name}")
    try:
        with pdfplumber.open(pdf_path) as pdf:
            text = ""
            for page in pdf.pages:
                page_text = page.extract_text()
                if page_text:
                    text += page_text + "\n"
            if text.strip():
                log_success(f"PDF 是文字版，成功提取 ({len(text)} 字)")
            else:
                log_warning("PDF 无有效文字（可能是扫描件）")
            return text.strip()
    except Exception as e:
        log_error(f"PDF 原生提取失败: {e}")
        return ""

def pdf_to_images(pdf_path: Path) -> list[Path]:
    log_info(f"将 PDF 转为图像 (dpi=200): {pdf_path.name}")
    images = convert_from_path(
        str(pdf_path),
        dpi=200,
        fmt="png",
        poppler_path=str(POPPLER_BIN_PATH)
    )
    img_paths = []
    for i, img in enumerate(images):
        img_path = IMG_DIR / f"{pdf_path.stem}_page_{i+1}.png"
        img.save(img_path, "PNG")
        img_paths.append(img_path)
    log_success(f"生成 {len(images)} 张图像")
    return img_paths

def extract_requirement_from_image(image_path: Path, project_name: str) -> str:
    global _OLLAMA_VL_FIRST_CALL
    if _OLLAMA_VL_FIRST_CALL:
        log_info(f"首次调用 Ollama VL 模型 '{OLLAMA_VL_MODEL}'，加载中...")
        _OLLAMA_VL_FIRST_CALL = False

    log_info(f"🖼️  正在分析图像: {image_path.name}")
    prompt = (
        f"你是一位政府采购专家。请从这张技术参数表中提取商品采购需求。\n"
        f"- 忽略页眉页脚、公司 logo、合同条款；\n"
        f"- 聚焦：商品名称、规格型号、技术参数、品牌要求、数量；\n"
        f"- 若有多个商品，请分别列出；\n"
        f"- 用一句简洁中文描述，以'本次采购需求为：'开头。\n\n"
        f"项目名称：{project_name}"
    )
    try:
        with open(image_path, "rb") as f:
            response = ollama.chat(
                model=OLLAMA_VL_MODEL,
                messages=[{"role": "user", "content": prompt, "images": [f.read()]}]
            )
        result = response["message"]["content"].strip()
        log_success(f"图像分析完成: {image_path.name}")
        return result
    except Exception as e:
        log_error(f"图像分析失败 {image_path.name}: {e}")
        raise RuntimeError(f"Ollama-VL 调用失败: {e}")

def ocr_entire_pdf(pdf_path: Path, project_name: str) -> str:
    log_info("⚠️ 检测到扫描版 PDF，启动 OCR 流程...")
    try:
        img_paths = pdf_to_images(pdf_path)
        results = []
        for img in img_paths:
            req = extract_requirement_from_image(img, project_name)
            if "本次采购需求为：" in req:
                results.append(req)
        final = "\n".join(results)
        log_success("OCR 流程全部完成")
        return final
    except Exception as e:
        log_error(f"OCR 流程失败: {e}")
        raise

def process_document(file_path: Path, project_name: str) -> str:
    suffix = file_path.suffix.lower()
    print(f"  📄 开始处理附件: {file_path.name} (类型: {suffix})")

    # 统一转 PDF
    pdf_path = None
    if suffix in ['.doc', '.docx', '.xls', '.xlsx']:
        try:
            pdf_path = office_to_pdf(file_path)
        except Exception as e:
            log_error(f"LibreOffice 转换失败: {e}")
            return ""
    elif suffix == '.pdf':
        pdf_path = file_path
    else:
        log_warning(f"不支持的文件类型: {suffix}")
        return ""

    if not pdf_path or not pdf_path.exists():
        return ""

    # 尝试文字提取
    text = extract_text_from_pdf_native(pdf_path)
    if text.strip():
        log_info("🧠 正在调用 qwen3:8b 分析文本内容...")
        start_time = time.time()
        prompt = (
            f"你是一位政府采购专家，请从以下文本中提取所有商品采购需求。\n"
            f"- 聚焦：商品名称、规格、数量、品牌要求；\n"
            f"- 若有多个商品，请分别列出；\n"
            f"- 用一句简洁中文描述，以'本次采购需求为：'开头。\n\n"
            f"项目名称：{project_name}\n\n{text[:5000]}"
        )
        response = ollama.chat(model="qwen3:8b", messages=[{"role": "user", "content": prompt}])
        result = response["message"]["content"].strip()
        elapsed = time.time() - start_time
        log_success(f"qwen3:8b 分析完成（耗时 {elapsed:.1f}s）")
        return result
    else:
        return ocr_entire_pdf(pdf_path, project_name)
