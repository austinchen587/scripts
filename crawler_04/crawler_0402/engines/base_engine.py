# engines/base_engine.py
from DrissionPage import ChromiumPage
try:
    from logger_helper import logger
except ImportError:
    import logging
    logger = logging.getLogger()

# [新增] 引入报警模块
from alert_helper import urgent_pause 

class BaseEngine:
    def __init__(self, browser):
        """
        [核心修复] 接收 main.py 传入的 browser 对象
        而不是自己去读取 BROWSER_ADDRESS 创建新连接
        """
        self.browser = browser
        self.tab = None

    def init_tab(self, platform_keyword):
        """
        初始化标签页逻辑
        """
        if not platform_keyword:
            self.tab = self.browser.latest_tab
            return True

        target_tab = None
        
        # 使用 .tab_ids 获取所有标签页ID
        try:
            all_ids = self.browser.tab_ids
        except:
            all_ids = getattr(self.browser, '_tab_ids', [])

        for t_id in all_ids:
            try:
                tab = self.browser.get_tab(t_id)
                if not tab: continue
                
                # 检查 URL 是否包含关键词
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
        
        # 激活标签页
        try:
            if hasattr(self.tab.set, 'activate'):
                self.tab.set.activate()
            elif hasattr(self.tab, 'activate'):
                self.tab.activate()
        except:
            pass 
            
        return True
    
    # ============================================================
    # 👉 [新增] 核心熔断检测：检查是否遇到验证码/登录
    # ============================================================
    def check_and_handle_verification(self, platform_name):
        """
        检测当前页面是否变成了 登录页 或 验证码页
        如果是，立即触发报警并挂起程序！
        """
        if not self.tab: return

        current_url = self.tab.url or ""
        page_text = ""
        try:
            # 只取前 2000 个字符快速检测，避免全文扫描太慢
            page_text = self.tab.html[:2000] 
        except: pass

        # === 1. 定义危险信号 (特征词) ===
        is_risk = False
        reason = ""

        # 通用特征
        if 'login' in current_url and 'search' not in current_url:
            is_risk = True; reason = "URL包含login"
        elif 'passport' in current_url: 
            is_risk = True; reason = "URL包含passport"
        elif 'validate' in current_url:
            is_risk = True; reason = "URL包含validate"
        
        # 京东特征
        elif platform_name == '京东' and ('验证一下' in page_text or '安全验证' in page_text):
            is_risk = True; reason = "页面包含'安全验证'"
        
        # 淘宝特征
        elif platform_name == '淘宝' and ('login.taobao' in current_url or '滑块' in page_text):
            is_risk = True; reason = "检测到淘宝滑块/登录"
            
        # 1688特征
        elif platform_name == '1688' and ('login.1688' in current_url or '拖动' in page_text):
            is_risk = True; reason = "检测到1688验证"

        # === 2. 触发熔断 ===
        if is_risk:
            # 调用 alert_helper 中的 urgent_pause
            # 这会 input() 阻塞住主线程，导致 main.py 停止调度新任务
            # 直到你在控制台按回车
            logger.error(f"🛑 [熔断] 检测到 {platform_name} 异常: {reason}")
            urgent_pause(platform_name, getattr(self.browser, '_custom_name', 'Unknown'))

    def random_wander(self, cards_list):
        """
        [反爬核心] 随机闲逛模式
        从当前页面的商品卡片中，随机选一个点进去看看，假装是真人在浏览
        """
        import random, time
        
        # 30% 的概率触发闲逛，70% 的概率不触发（太频繁也不像人）
        if not cards_list or random.random() > 0.3:
            return

        logger.info("🚶 [行为模拟] 触发随机闲逛：正在挑选一个商品假装查看...")
        
        try:
            # 1. 随机选一个卡片
            target_card = random.choice(cards_list)
            
            # 2. 尝试寻找链接并点击 (兼容 JD/TB/1688)
            # 大多数商品卡片里的 a 标签都是跳转链接
            link_ele = target_card.ele('tag:a', timeout=1) or target_card
            
            # 记录当前的标签页数量
            initial_count = self.browser.tabs_count
            
            # 点击 (使用 JS 点击防止被遮挡)
            link_ele.click(by_js=True)
            time.sleep(2) # 等待浏览器反应
            
            # 3. 判断是“新标签页打开”还是“本页跳转”
            if self.browser.tabs_count > initial_count:
                # === 情况 A: 打开了新标签页 (大多数情况) ===
                new_tab = self.browser.latest_tab
                logger.info(f"   -> 👀 [New Tab] 正在浏览详情页: {new_tab.title[:15]}...")
                
                # 随机停留 3-8 秒 (模拟人类阅读)
                time.sleep(random.uniform(3, 8))
                
                # 随机滚动一下
                new_tab.scroll.down(random.randint(300, 600))
                time.sleep(1)
                
                # 关闭详情页
                new_tab.close()
                logger.info("   -> 🔙 关闭详情页，回到搜索列表")
                
            else:
                # === 情况 B: 在当前页跳转了 (较少见) ===
                logger.info("   -> 👀 [Same Tab] 正在浏览详情页...")
                time.sleep(random.uniform(3, 6))
                self.browser.back() # 后退
                logger.info("   -> 🔙 后退操作，回到搜索列表")
                self.browser.wait(1) # 等待后退渲染
                
        except Exception as e:
            logger.warning(f"⚠️ [行为模拟] 闲逛失败 (不影响主流程): {e}")