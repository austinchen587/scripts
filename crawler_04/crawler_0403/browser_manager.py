# browser_manager.py
import random
import time
import os
from DrissionPage import ChromiumPage, ChromiumOptions
from config import CHROME_DATA_BASE 
from logger_helper import logger

# 纯 Windows 环境的 User-Agent 池 (严禁混入 Mac/Linux UA)
UA_LIST = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36 Edg/126.0.0.0" # 混入一个 Edge 浏览器伪装
]

class BrowserPool:
    def __init__(self):
        self.browsers = {}
        
       
        for i in range(1, 4): 
            path = os.path.join(CHROME_DATA_BASE, f'user_{i}')
            if not os.path.exists(path):
                try:
                    os.makedirs(path, exist_ok=True)
                    logger.info(f"📂 创建数据目录: {path}")
                except Exception as e:
                    logger.error(f"❌ 创建目录失败: {path}, 错误: {e}")

        # [修改] 只保留 Browser_Worker_1 的配置，删掉另外两个，省下大量内存！
        self.configs = [
            {'name': '京东', 'port': 9222, 'user_data': os.path.join(CHROME_DATA_BASE, 'user_1'), 'pos': (0, 0)},
            {'name': '1688', 'port': 9223, 'user_data': os.path.join(CHROME_DATA_BASE, 'user_2'), 'pos': (50, 50)},
            {'name': '淘宝', 'port': 9224, 'user_data': os.path.join(CHROME_DATA_BASE, 'user_3'), 'pos': (100, 100)}
        ]

    def start_all(self):
        logger.info(f"🚀 [Manager] 正在启动 {len(self.configs)} 个潜行浏览器矩阵...")
        logger.info(f"📂 [Storage] 数据存储: {CHROME_DATA_BASE}")
        
        self.browsers = {}

        for i, cfg in enumerate(self.configs):
            logger.info(f"   -> 正在启动第 {i+1} 个: {cfg['name']} (Port: {cfg['port']})...")
            try:
                co = ChromiumOptions()
                co.set_local_port(cfg['port'])
                co.set_user_data_path(cfg['user_data'])
                co.set_argument('--no-first-run')
                
                # ==========================================
                # 🛡️ 核心防封配置：Windows 终极潜行
                # ==========================================
                # 1. 抹除自动化核心特征
                co.set_argument('--disable-blink-features=AutomationControlled')
                # 2. 隐藏提示条和无用扩展
                co.set_argument('--disable-infobars')
                co.set_argument('--disable-extensions')
                co.set_argument('--disable-gpu-shader-disk-cache')
                # 3. 随机化窗口，避免固定分辨率被标记
                win_w = random.choice([1366, 1440, 1600, 1920])
                win_h = random.choice([768, 900, 1024, 1080])
                co.set_argument(f'--window-size={win_w},{win_h}')
                
                x, y = cfg.get('pos', (i*50, i*50))
                co.set_argument(f'--window-position={x},{y}')
                co.set_argument('--restore-last-session')

                my_ua = UA_LIST[i % len(UA_LIST)]
                co.set_user_agent(my_ua)

                page = ChromiumPage(addr_or_opts=co)
                page._custom_name = cfg['name'] 
                
                # ==========================================
                # 💉 核心防封配置：运行时注入 Stealth JS
                # ==========================================
                # 让每一个新打开的标签页都自动执行这些代码，伪装成正常浏览器
                stealth_js = """
                    Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
                    window.navigator.chrome = { runtime: {}, };
                    Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
                    Object.defineProperty(navigator, 'languages', { get: () => ['zh-CN', 'zh', 'en'] });
                """
                page.run_cdp('Page.addScriptToEvaluateOnNewDocument', source=stealth_js)
                
                self.browsers[cfg['name']] = page
                logger.info(f"   ✅ [{cfg['name']}] 隐形启动成功！")
                time.sleep(3) 
                
            except Exception as e:
                logger.error(f"   ❌ [{cfg['name']}] 启动失败: {e}")

        if not self.browsers:
            raise Exception("❌ 严重错误：没有任何浏览器启动成功！请检查 Chrome 是否被占用。")

    
    def check_all_browsers_ready(self):
        """
        检查池中所有浏览器是否都处于“搜索状态”
        """
        not_ready_names = []
        # 👉 [修改] 遍历字典必须用 .items()，同时拿出名字和浏览器对象
        for b_name, browser in self.browsers.items():
            is_ready = False
            try:
                try: tab_ids = browser.tab_ids
                except: tab_ids = getattr(browser, '_tab_ids', [])

                for t_id in tab_ids:
                    tab = browser.get_tab(t_id)
                    url = tab.url.lower() if tab.url else ""
                    if ('search' in url) or ('s.taobao.com' in url) or \
                       ('s.1688.com' in url) or ('keyword=' in url) or ('q=' in url):
                        is_ready = True
                        break
            except: pass
            
            if not is_ready:
                not_ready_names.append(b_name)
        
        return (len(not_ready_names) == 0), not_ready_names

# 初始化单例
pool = BrowserPool()