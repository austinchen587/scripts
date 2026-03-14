# document_processor/config.py
import os
import sys

# 项目根目录 
PROJECT_ROOT = r"D:\code\project\scripts\20251227\20260111_step_2"
DOWNLOAD_DIR = os.path.join(PROJECT_ROOT, "downloads")

def _get_platform_paths():
    """根据平台返回正确的路径"""
    if os.name == 'nt':  # Windows
        # Windows路径配置
        libreoffice_path = r"D:\libreoffice\program\soffice.exe"
        poppler_bin_path = r"D:\poppler-25.12.0\poppler-25.12.0\Library\bin"
        
        # 验证路径存在
        if not os.path.exists(libreoffice_path):
            print(f"⚠️ LibreOffice路径不存在: {libreoffice_path}")
            libreoffice_path = "soffice"  # 回退到系统PATH
            
        if not os.path.exists(poppler_bin_path):
            print(f"⚠️ Poppler路径不存在: {poppler_bin_path}")
            poppler_bin_path = None
            
        return libreoffice_path, poppler_bin_path
    else:  # macOS/Linux
        # macOS路径查找函数
        def _find_soffice_mac():
            candidates = [
                "/Applications/LibreOffice.app/Contents/MacOS/soffice",
                "/usr/local/bin/soffice",
                "/opt/homebrew/bin/soffice"
            ]
            for path in candidates:
                if os.path.exists(path):
                    return path
            return "soffice"
        
        def _find_poppler_path():
            poppler_bin = "/opt/homebrew/bin"
            if os.path.exists(poppler_bin):
                return poppler_bin
            return None
            
        return _find_soffice_mac(), _find_poppler_path()

# 根据平台设置路径
LIBREOFFICE_PATH, POPPLER_BIN_PATH = _get_platform_paths()

print(f"[CONFIG] ✅ 平台检测: {os.name}")
print(f"[CONFIG] 📁 下载目录: {DOWNLOAD_DIR}")
print(f"[CONFIG] 📄 LibreOffice: {LIBREOFFICE_PATH}")
print(f"[CONFIG] 📊 Poppler: {POPPLER_BIN_PATH or '未设置'}")

# 如果Poppler路径有效，确保在环境变量中
if POPPLER_BIN_PATH and os.path.exists(POPPLER_BIN_PATH):
    if POPPLER_BIN_PATH not in os.environ.get('PATH', ''):
        # Windows用分号分隔，其他用冒号
        separator = ';' if os.name == 'nt' else ':'
        os.environ['PATH'] = f"{POPPLER_BIN_PATH}{separator}{os.environ.get('PATH', '')}"
        print(f"[CONFIG] 🔧 已添加Poppler到PATH")
    
    # 验证关键文件是否存在
    if os.name == 'nt':  # Windows
        pdftoppm_exe = os.path.join(POPPLER_BIN_PATH, 'pdftoppm.exe')
        if not os.path.exists(pdftoppm_exe):
            print(f"⚠️ 找不到pdftoppm.exe: {pdftoppm_exe}")
    else:  # macOS/Linux
        pdftoppm_exe = os.path.join(POPPLER_BIN_PATH, 'pdftoppm')
        if not os.path.exists(pdftoppm_exe):
            print(f"⚠️ 找不到pdftoppm: {pdftoppm_exe}")
