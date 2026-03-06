# browser_manager.py
import random
import time
import os
from DrissionPage import ChromiumPage, ChromiumOptions
from config import CHROME_DATA_BASE 
from logger_helper import logger

# 准备足够的 UserAgent 池
UA_LIST = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36 Edg/119.0.0.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_2_1) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"
]

class BrowserPool:
    def __init__(self):
        self.browsers = []
        
        # [修改] 循环范围改为 1 到 2 (只创建 user_1 目录)
        for i in range(1, 2): 
            path = os.path.join(CHROME_DATA_BASE, f'user_{i}')
            if not os.path.exists(path):
                try:
                    os.makedirs(path, exist_ok=True)
                    logger.info(f"📂 创建数据目录: {path}")
                except Exception as e:
                    logger.error(f"❌ 创建目录失败: {path}, 错误: {e}")

        # [修改] 只保留 Browser_Worker_1 的配置，删掉另外两个，省下大量内存！
        self.configs = [
            # 浏览器 1
            {
                'name': 'Browser_Worker_1', 
                'port': 9222, 
                'user_data': os.path.join(CHROME_DATA_BASE, 'user_1'),
                'pos': (0, 0)
            }
        ]

    def start_all(self):
        logger.info(f"🚀 [Manager] 正在启动 {len(self.configs)} 个浏览器矩阵...")
        logger.info(f"📂 [Storage] 数据存储: {CHROME_DATA_BASE}")
        
        self.browsers = []

        for i, cfg in enumerate(self.configs):
            logger.info(f"   -> 正在启动第 {i+1} 个: {cfg['name']} (Port: {cfg['port']})...")
            try:
                co = ChromiumOptions()
                co.set_local_port(cfg['port'])
                co.set_user_data_path(cfg['user_data'])
                co.set_argument('--no-first-run')
                
                # 设置窗口位置和大小，防止重叠
                x, y = cfg.get('pos', (i*50, i*50))
                co.set_argument(f'--window-position={x},{y}')
                co.set_argument(f'--window-size=1200,800')
                
                # 关键：恢复上次会话 (记住登录状态)
                co.set_argument('--restore-last-session')

                # 注入 UA
                my_ua = UA_LIST[i % len(UA_LIST)]
                co.set_user_agent(my_ua)

                # 启动浏览器对象
                page = ChromiumPage(addr_or_opts=co)
                
                # 强制标记名字
                page._custom_name = cfg['name'] 
                
                # 加入池子
                self.browsers.append(page)
                
                logger.info(f"   ✅ [{cfg['name']}] 启动成功！")
                
                # 间隔 3 秒，防止 CPU 瞬间飙升
                time.sleep(3) 
                
            except Exception as e:
                logger.error(f"   ❌ [{cfg['name']}] 启动失败: {e}")
                import traceback
                logger.error(traceback.format_exc())

        if not self.browsers:
            raise Exception("❌ 严重错误：没有任何浏览器启动成功！请检查 Chrome 是否被占用。")
        
        logger.info(f"🎉 3 矩阵启动完毕，共 {len(self.browsers)} 个窗口。")

    def get_random_browser(self):
        if not self.browsers:
            raise Exception("没有可用的浏览器实例！")
        return random.choice(self.browsers)

    def check_all_browsers_ready(self):
        """
        检查池中所有浏览器是否都处于“搜索状态”
        """
        not_ready_names = []
        for browser in self.browsers:
            is_ready = False
            b_name = getattr(browser, '_custom_name', 'Unknown')
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