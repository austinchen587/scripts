import re
import requests
from urllib.parse import urljoin, urlparse
from pathlib import Path
from config import ATTACH_DIR

REQUEST_HEADERS = {
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "Accept-Encoding": "gzip, deflate, br, zstd",
    "Accept-Language": "en,zh;q=0.9,zh-CN;q=0.8",
    "Connection": "keep-alive",
    "Cookie": "_zcy_log_client_uuid=f1280000-e2d4-11f0-9905-79019a6a82b3; districtCode=369900; districtName=%E6%B1%9F%E8%A5%A5%E7%9C%81%E6%9C%AC%E7%BA%A7; districtType=010100",
    "Referer": "https://www.jxemall.com/luban/bidding/detail?requisitionId=62026010977990433&type=BIDDING_INVITATION",
    "Sec-Fetch-Dest": "empty",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Site": "same-origin",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36",
    "X-Requested-With": "XMLHttpRequest",
    "sec-ch-ua": '"Google Chrome";v="143", "Chromium";v="143", "Not A(Brand";v="24"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"Windows"'
}

def sanitize_filename(name: str) -> str:
    """安全化文件名：移除非法字符，优先保留扩展名"""
    parts = name.rsplit('.', 1)
    if len(parts) == 2 and len(parts[1]) <= 10 and parts[1].replace('_', '').isalnum():
        base, ext = parts
        safe_base = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', base)
        return (safe_base[:95] + '.' + ext) if len(safe_base) > 95 else f"{safe_base}.{ext}"
    else:
        safe_name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', name)
        return safe_name[:100]

def is_likely_document_file(file_path: Path) -> bool:
    try:
        with open(file_path, 'rb') as f:
            header = f.read(8)
        if header.startswith(b'%PDF'):
            return True
        if header.startswith(b'PK\x03\x04') or header.startswith(b'PK\x05\x06') or header.startswith(b'PK\x07\x08'):
            return True
        if header.startswith(b'\xD0\xCF\x11\xE0\xA1\xB1\x1A\xE1'):
            return True
        return False
    except Exception:
        return False

def download_attachment(url: str, project_name: str) -> Path | None:
    try:
        resp = requests.get(url, headers=REQUEST_HEADERS, timeout=30)
        resp.raise_for_status()

        filename = None
        if "content-disposition" in resp.headers:
            cd = resp.headers["content-disposition"]
            if "filename=" in cd:
                filename = cd.split("filename=")[1].strip('"')
        if not filename:
            parsed = urlparse(url)
            filename = Path(parsed.path).name or "attachment.bin"

        safe_proj = sanitize_filename(project_name)
        safe_file = sanitize_filename(filename)
        final_name = f"{safe_proj}_{safe_file}"
        save_path = ATTACH_DIR / final_name

        with open(save_path, "wb") as f:
            f.write(resp.content)

        if not is_likely_document_file(save_path):
            print(f"  ⚠️ 文件 {save_path.name} 不是有效文档（可能为 HTML/错误页），已删除")
            save_path.unlink(missing_ok=True)
            return None

        return save_path

    except Exception as e:
        print(f"⚠️ 下载失败 {url}: {e}")
        return None
