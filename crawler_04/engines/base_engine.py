# engines/base_engine.py
from DrissionPage import ChromiumPage
from config import BROWSER_ADDRESS
try:
    from logger_helper import logger
except ImportError:
    import logging
    logger = logging.getLogger()

class BaseEngine:
    def __init__(self):
        # 使用 ChromiumPage
        self.browser = ChromiumPage(addr_or_opts=BROWSER_ADDRESS)
        self.tab = None

    def init_tab(self, platform_keyword):
        """
        初始化标签页逻辑 (修复 'no attribute tabs' 报错)
        使用 tab_ids 来遍历，兼容性最强
        """
        if not platform_keyword:
            self.tab = self.browser.latest_tab
            return True

        target_tab = None
        
        # [核心修复] 使用 .tab_ids 获取所有标签页ID，而不是直接调用 .tabs
        # 这样可以避免 AttributeError
        try:
            all_ids = self.browser.tab_ids
        except:
            # 极少数旧版本可能是 _tab_ids，做个兜底
            all_ids = getattr(self.browser, '_tab_ids', [])

        for t_id in all_ids:
            # 通过 ID 获取具体的 Tab 对象
            try:
                tab = self.browser.get_tab(t_id)
                if not tab: continue
                
                # 检查 URL 是否包含关键词 (如 'jd', '1688')
                # 加个 or "" 防止 url 是 None
                if platform_keyword in (tab.url or ""):
                    target_tab = tab
                    logger.info(f"🔄 [System] 复用已存在的 '{platform_keyword}' 标签页")
                    break
            except Exception:
                continue
        
        # 如果没找到，新建标签页
        if not target_tab:
            logger.info(f"🆕 [System] 为 '{platform_keyword}' 新建标签页...")
            target_tab = self.browser.new_tab()
        
        self.tab = target_tab
        
        # [兼容性修复] 激活标签页
        try:
            # v4.x 新版写法
            if hasattr(self.tab.set, 'activate'):
                self.tab.set.activate()
            # v3.x 旧版写法
            elif hasattr(self.tab, 'activate'):
                self.tab.activate()
        except:
            pass # 激活失败不影响核心功能
            
        return True