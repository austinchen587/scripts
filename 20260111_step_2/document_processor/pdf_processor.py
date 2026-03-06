# document_processor/pdf_processor.py
import tempfile
import os  # 添加这行
from pathlib import Path
import pdfplumber
from pdf2image import convert_from_path
from .config import POPPLER_BIN_PATH, DOWNLOAD_DIR

def extract_text_native(pdf_path: Path) -> str:
    """尝试原生提取 PDF 文字"""
    try:
        with pdfplumber.open(pdf_path) as pdf:
            text = ""
            for page in pdf.pages:
                t = page.extract_text()
                if t:
                    text += t + "\n"
            return text.strip()
    except Exception:
        return ""

def pdf_to_images(pdf_path: Path) -> list[Path]:
    """将 PDF 转为 PNG 图像列表"""
    try:
        # 修复：先检查并确保Poppler路径能被找到
        poppler_path = POPPLER_BIN_PATH
        
        # 如果设置了Poppler路径但不在环境变量中，临时添加到PATH
        if poppler_path and os.path.exists(poppler_path):
            if poppler_path not in os.environ.get('PATH', ''):
                os.environ['PATH'] = f"{poppler_path};{os.environ.get('PATH', '')}"
                print(f"[PDF] 🔧 已添加路径到环境变量: {poppler_path}")
            
            # 检查关键文件是否存在
            pdftoppm_file = Path(poppler_path) / "pdftoppm.exe"
            if not pdftoppm_file.exists():
                print(f"[PDF] ⚠️ 找不到pdftoppm.exe，检查路径: {poppler_path}")
        
        images = convert_from_path(
            str(pdf_path),
            dpi=200,
            fmt="png",
            poppler_path=poppler_path
        )
        img_paths = []
        temp_dir = Path(tempfile.mkdtemp(dir=DOWNLOAD_DIR))
        for i, img in enumerate(images):
            img_path = temp_dir / f"{pdf_path.stem}_page_{i+1}.png"
            img.save(img_path, "PNG")
            img_paths.append(img_path)
        return img_paths
    except Exception as e:
        print(f"[PDF] ⚠️ PDF转图片失败: {str(e)}")
        
        # 提供具体的错误信息
        if "Unable to get page count" in str(e):
            print(f"[PDF] 🔧 Poppler路径问题，请检查: {POPPLER_BIN_PATH}")
            print(f"[PDF] 🔧 确保pdftoppm.exe文件存在")
            print(f"[PDF] 🔧 当前PATH环境变量: {os.environ.get('PATH', '')[:200]}...")
        
        return []

def extract_text_with_table_enhancement(pdf_path: Path) -> str:
    """
    增强表格识别的文本提取 - Markdown格式化版
    策略：将检测到的表格转换为Markdown格式，帮助LLM理解结构
    """
    try:
        full_text = ""
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                # 1. 优先提取表格并转为 Markdown
                tables = page.extract_tables()
                if tables:
                    full_text += f"\n\n--- 第 {page.page_number} 页表格区域 ---\n"
                    for table in tables:
                        # 过滤空行和过短的行
                        valid_rows = [row for row in table if row and any(cell and str(cell).strip() for cell in row)]
                        if not valid_rows:
                            continue

                        # 构建 Markdown 表格
                        md_table = ""
                        # 处理表头
                        headers = [str(cell).strip().replace('\n', ' ') if cell else "  " for cell in valid_rows[0]]
                        md_table += "| " + " | ".join(headers) + " |\n"
                        md_table += "| " + " | ".join(["---"] * len(headers)) + " |\n"
                        
                        # 处理数据行
                        for row in valid_rows[1:]:
                            cells = [str(cell).strip().replace('\n', ' ') if cell else "  " for cell in row]
                            md_table += "| " + " | ".join(cells) + " |\n"
                        
                        full_text += md_table + "\n"
                    full_text += "--- 表格区域结束 ---\n\n"

                # 2. 提取普通文本（作为补充）
                text = page.extract_text()
                if text:
                    # 简单过滤掉已经在表格里提取过的内容可能比较复杂，这里直接追加，靠LLM去重
                    full_text += text + "\n"
        
        return full_text.strip()
    except Exception as e:
        print(f"[PDF] ⚠️ 表格增强提取失败: {e}")
        # 回退到普通提取
        try:
            from document_processor import extract_text_native
            return extract_text_native(pdf_path)
        except:
            return ""