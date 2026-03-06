# file_downloader.py - 优化去重版本
import os
import re
import requests
from urllib.parse import urljoin, urlparse, unquote, urlencode, parse_qs
from pathlib import Path
from typing import Union, Dict, Set
from config import DOWNLOAD_DIR

# === 复用你的请求头 ===
REQUEST_HEADERS = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en,zh;q=0.9,zh-CN;q=0.8",
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Referer": "https://www.jxemall.com/",
    "Connection": "keep-alive",
}

def sanitize_filename(name: str) -> str:
    """安全化文件名：移除非法字符"""
    parts = name.rsplit('.', 1)
    if len(parts) == 2 and len(parts[1]) <= 10 and parts[1].replace('_', '').isalnum():
        base, ext = parts
        safe_base = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', base)
        return (safe_base[:95] + '.' + ext) if len(safe_base) > 95 else f"{safe_base}.{ext}"
    else:
        safe_name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', name)
        return safe_name[:100]

def normalize_url(url: str) -> str:
    """标准化URL，便于去重比较
    
    处理方式：
    1. 移除不必要的查询参数（如sessionid、timestamp等）
    2. 统一参数顺序
    3. 保留关键参数（如file_id、doc_id等）
    """
    try:
        parsed = urlparse(url)
        
        # 如果URL中没有查询参数，直接返回
        if not parsed.query:
            return url
            
        # 解析查询参数
        params = parse_qs(parsed.query)
        
        # 定义需要保留的关键参数（通常与文件相关的参数）
        key_file_params = {
            'file', 'file_id', 'fileid', 'id', 'doc', 'doc_id', 'docid',
            'attachment', 'att', 'filename', 'name', 'download'
        }
        
        # 过滤参数：保留关键文件参数，移除动态参数
        filtered_params = {}
        for key, values in params.items():
            key_lower = key.lower()
            
            # 判断是否为关键文件参数
            is_file_param = False
            for keyword in key_file_params:
                if keyword in key_lower:
                    is_file_param = True
                    break
            
            # 判断是否为动态参数（通常是无意义的）
            is_dynamic_param = any(word in key_lower for word in [
                'timestamp', 'time', 'ts', 
                'session', 'token', 'auth',
                'random', 'rand', 
                'callback', 'cb',
                'sign', 'signature',
                'v', 'version'
            ])
            
            if is_file_param and not is_dynamic_param:
                # 取第一个值
                if values:
                    filtered_params[key] = values[0]
        
        # 构建新的查询字符串（按字母排序，保证一致性）
        if filtered_params:
            sorted_params = sorted(filtered_params.items())
            new_query = urlencode(sorted_params)
            
            # 重建URL
            new_parsed = parsed._replace(query=new_query)
            normalized = new_parsed.geturl()
            
            # 如果标准化后与原始URL不同，打印日志
            if normalized != url:
                print(f"[URL NORMALIZE] 🔄 {url[:80]}... → {normalized[:80]}...")
            
            return normalized
        else:
            # 如果没有关键参数，只保留基础URL（移除所有查询参数）
            new_parsed = parsed._replace(query='')
            return new_parsed.geturl()
            
    except Exception as e:
        print(f"[URL NORMALIZE] ⚠️ 标准化失败 {url}: {e}")
        # 失败时返回原始URL
        return url

def check_same_file_by_content(url1: str, url2: str) -> bool:
    """通过请求部分内容判断两个URL是否指向同一文件（可选）"""
    try:
        # 只请求头部信息，不下载完整文件
        resp1 = requests.head(url1, headers=REQUEST_HEADERS, timeout=5, allow_redirects=True)
        resp2 = requests.head(url2, headers=REQUEST_HEADERS, timeout=5, allow_redirects=True)
        
        if resp1.status_code == 200 and resp2.status_code == 200:
            # 比较内容长度
            size1 = resp1.headers.get('content-length')
            size2 = resp2.headers.get('content-length')
            
            # 比较内容类型
            type1 = resp1.headers.get('content-type', '').split(';')[0]
            type2 = resp2.headers.get('content-type', '').split(';')[0]
            
            # 比较ETag（文件指纹）
            etag1 = resp1.headers.get('etag')
            etag2 = resp2.headers.get('etag')
            
            # 如果ETag相同，可以确定是同一文件
            if etag1 and etag2 and etag1 == etag2:
                return True
                
            # 如果长度和类型都相同，可能是同一文件
            if size1 and size2 and size1 == size2 and type1 == type2:
                return True
                
    except Exception as e:
        # 如果HEAD请求失败，返回False（不阻止后续下载）
        print(f"[SAME FILE CHECK] ⚠️ 检查失败: {e}")
    
    return False

def is_likely_valid_file(file_path: Path) -> bool:
    """通过文件头判断是否为有效文档或图片"""
    try:
        with open(file_path, 'rb') as f:
            header = f.read(12)  # 读取更多字节以覆盖所有格式
            
        # === 文档格式 ===
        # PDF
        if header.startswith(b'%PDF'):
            return True
        # ZIP-based (DOCX, XLSX, PPTX)
        if header.startswith(b'PK\x03\x04') or header.startswith(b'PK\x05\x06'):
            return True
        # DOC (OLE)
        if header.startswith(b'\xD0\xCF\x11\xE0\xA1\xB1\x1A\xE1'):
            return True
        # RTF
        if header.startswith(b'{\\rtf'):
            return True
            
        # === 图片格式 ===
        # JPEG
        if header.startswith(b'\xFF\xD8\xFF'):
            return True
        # PNG
        if header.startswith(b'\x89PNG\r\n\x1a\n'):
            return True
        # GIF
        if header.startswith(b'GIF87a') or header.startswith(b'GIF89a'):
            return True
        # BMP
        if header.startswith(b'BM'):
            return True
        # TIFF
        if header.startswith(b'II*\x00') or header.startswith(b'MM\x00*'):
            return True
        # WebP
        if header.startswith(b'RIFF') and len(header) >= 12 and header[8:12] == b'WEBP':
            return True
            
        # === 检查文件扩展名（备用方案）===
        ext = file_path.suffix.lower()
        valid_extensions = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff', '.webp', 
                           '.pdf', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx'}
        if ext in valid_extensions:
            return True
            
        return False
    except Exception:
        return False

class DownloadTracker:
    """跟踪下载记录，避免重复下载"""
    
    def __init__(self):
        # 记录已经下载过的URL（标准化后的）
        self.downloaded_urls: Set[str] = set()
        # URL到本地文件路径的映射
        self.url_to_path: Dict[str, str] = {}
        
    def add_download(self, url: str, file_path: str):
        """添加下载记录"""
        normalized = normalize_url(url)
        self.downloaded_urls.add(normalized)
        self.url_to_path[normalized] = file_path
        
    def check_already_downloaded(self, url: str) -> Union[str, None]:
        """检查URL是否已下载，返回本地文件路径或None"""
        normalized = normalize_url(url)
        
        if normalized in self.downloaded_urls:
            if normalized in self.url_to_path:
                file_path = self.url_to_path[normalized]
                # 检查文件是否还存在
                if os.path.exists(file_path):
                    return file_path
                else:
                    # 文件已删除，清除记录
                    del self.url_to_path[normalized]
                    self.downloaded_urls.remove(normalized)
        
        return None

# 创建全局下载跟踪器
_tracker = DownloadTracker()

def download_file(url: str, project_name: str = "") -> Union[str, None]:
    """
    下载单个附件，带文件名校验和内容验证
    """
    try:
        # 检查是否已下载过此URL
        existing_file = _tracker.check_already_downloaded(url)
        if existing_file:
            print(f"🔄 文件已存在（基于URL去重）: {os.path.basename(existing_file)}")
            return existing_file
        
        resp = requests.get(url, headers=REQUEST_HEADERS, timeout=30)
        resp.raise_for_status()

        # 检查内容类型，如果不是有效文件类型则跳过
        content_type = resp.headers.get('content-type', '').lower()
        if any(x in content_type for x in ['text/html', 'application/json']):
            print(f"⚠️ 跳过HTML/JSON文件: {url}")
            return None

        # 尝试从 Content-Disposition 获取文件名
        filename = None
        if "content-disposition" in resp.headers:
            cd = resp.headers["content-disposition"]
            if "filename=" in cd:
                filename = cd.split("filename=")[-1].strip().strip('"')
        if not filename:
            parsed = urlparse(url)
            filename = unquote(Path(parsed.path).name) or "attachment.bin"

        # 安全化文件名，并加上项目前缀（便于追踪）
        safe_file = sanitize_filename(filename)
        if project_name:
            safe_proj = sanitize_filename(project_name)
            final_name = f"{safe_proj}_{safe_file}"
        else:
            final_name = safe_file

        save_path = Path(DOWNLOAD_DIR) / final_name

        # 如果文件已存在，跳过下载
        if save_path.exists():
            print(f"✅ 文件已存在: {save_path.name}")
            _tracker.add_download(url, str(save_path))
            return str(save_path)

        # 保存
        with open(save_path, "wb") as f:
            f.write(resp.content)

        # 验证是否为真实文档或图片
        if not is_likely_valid_file(save_path):
            print(f"⚠️ 文件 {save_path.name} 不是有效文档/图片，已删除")
            save_path.unlink(missing_ok=True)
            return None

        print(f"✅ 下载成功: {save_path.name}")
        _tracker.add_download(url, str(save_path))
        return str(save_path)

    except Exception as e:
        print(f"❌ 下载失败 {url}: {e}")
        return None

def download_attachments(urls: Union[list[str], None], project_name: str = "") -> list[str]:
    """
    批量下载附件（增强去重版本）
    """
    if not urls:
        return []
    
    # URL去重和清理
    unique_urls = []
    seen_filenames = {}  # 保存文件名到URL的映射，避免相同文件名重复下载
    
    for url in urls:
        if isinstance(url, str) and url.strip():
            clean_url = url.strip()
            
            # 标准化URL作为去重依据
            normalized_url = normalize_url(clean_url)
            
            # 提取可能的基本文件名
            parsed = urlparse(clean_url)
            path_filename = unquote(Path(parsed.path).name) or "unknown"
            
            # 如果遇到相同的文件名，检查是否是同一文件的不同版本
            if path_filename in seen_filenames and path_filename != "unknown":
                existing_url = seen_filenames[path_filename]
                # 检查是否可能是同一文件
                if check_same_file_by_content(existing_url, clean_url):
                    print(f"🔄 跳过可能重复文件: {path_filename}")
                    continue
            
            # 添加到列表
            if normalized_url not in [normalize_url(u) for u in unique_urls]:
                unique_urls.append(clean_url)
                seen_filenames[path_filename] = clean_url
    
    print(f"[DOWNLOAD] 🔄 原始URL: {len(urls)} → 去重后: {len(unique_urls)}")
    
    paths = []
    download_stats = {
        'success': 0,
        'skipped': 0,
        'failed': 0
    }
    
    for url in unique_urls:
        p = download_file(url, project_name)
        if p:
            paths.append(p)
            download_stats['success'] += 1
        elif p is None:  # 返回None表示跳过
            download_stats['skipped'] += 1
        else:  # 返回False表示失败
            download_stats['failed'] += 1
    
    print(f"[DOWNLOAD] 📊 统计: 成功={download_stats['success']}, "
          f"跳过={download_stats['skipped']}, 失败={download_stats['failed']}")
    
    return paths

def cleanup_attachments(attachment_paths: list[str]):
    """
    清理附件文件（处理完后调用）
    """
    if not attachment_paths:
        return 0
    
    deleted_count = 0
    for path in attachment_paths:
        try:
            if os.path.exists(path):
                os.remove(path)
                deleted_count += 1
                print(f"[CLEANUP] 🗑️ 已删除: {os.path.basename(path)}")
        except Exception as e:
            print(f"[CLEANUP] ⚠️ 删除失败 {path}: {e}")
    
    print(f"[CLEANUP] ✅ 清理完成，共删除 {deleted_count} 个文件")
    return deleted_count
