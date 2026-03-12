# document_processor/libreoffice_utils.py
import subprocess
from pathlib import Path
from .config import LIBREOFFICE_PATH

def office_to_pdf(input_path: Path) -> Path:
    """将 Office 文件转为 PDF"""
    output_pdf = input_path.with_suffix('.pdf')
    if output_pdf.exists():
        return output_pdf
    cmd = [
        LIBREOFFICE_PATH,
        "--headless",
        "--convert-to", "pdf",
        "--outdir", str(input_path.parent),
        str(input_path)
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    if result.returncode != 0 or not output_pdf.exists():
        raise RuntimeError(f"LibreOffice 转换失败: {result.stderr}")
    return output_pdf
