# engines/base_engine.py
from DrissionPage import ChromiumPage
try:
    from logger_helper import logger
except ImportError:
    import logging
    logger = logging.getLogger()

# [新增] 引入报警模块
from alert_helper import urgent_pause 


# 1. 在顶部定义一个自定义异常
class AntiSpiderException(Exception):
    def __init__(self, platform_name, reason):
        self.platform_name = platform_name
        self.reason = reason
        super().__init__(f"[{platform_name}] 触发风控: {reason}")

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
        检测当前页面是否变成了 登录页、验证码页 或 风控警告页
        如果是，立即触发异常并交由调度器挂起/重试！
        """
        if not self.tab: return

        current_url = self.tab.url or ""
        page_text = ""
        try:
            # 👉 [优化] 将快速检测的字符量从 2000 提升到 5000，防止风控提示在 HTML 中部被截断
            page_text = self.tab.html[:5000] 
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
        
        # 淘宝特征 (👉 深度优化：增加账号异常行为拦截)
        elif platform_name == '淘宝':
            if 'login.taobao' in current_url or '滑块' in page_text:
                is_risk = True; reason = "检测到淘宝滑块/登录"
            elif '访问行为存在异常' in page_text or '涉嫌不当获取' in page_text:
                is_risk = True; reason = "淘宝账号行为级风控警告(极危)"
            
        # 1688特征
        elif platform_name == '1688' and ('login.1688' in current_url or '拖动' in page_text):
            is_risk = True; reason = "检测到1688验证"

        # === 2. 触发熔断 ===
        if is_risk:
            # 抛出异常，打断当前流程，让 main.py 捕获并执行洗白和挂起逻辑
            logger.error(f"🛑 [熔断] 检测到 {platform_name} 异常: {reason}")
            raise AntiSpiderException(platform_name, reason)

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

    # ============================================================
    # 👉 [新增] 详情页混合回采：动态寻址点击 + 纯文本 + 长截图
    # ============================================================
    def fetch_detail_specs(self, detail_url, sku, platform, target_specs):
        import random, time, os
        from config import DATA_DIR
        
        screenshot_dir = os.path.join(DATA_DIR, 'screenshots')
        os.makedirs(screenshot_dir, exist_ok=True)
        image_save_path = os.path.join(screenshot_dir, f"{platform}_{sku}.png")
        result_data = {"text": "", "image_path": ""}

        try:
            logger.info(f"   -> 🔎 [深入回采] 正在潜入 {platform} 详情页: {sku}")
            self.tab = self.browser.new_tab(detail_url)
            time.sleep(random.uniform(2, 4))
            
            # 🎯 核心防骗：跨平台规格按钮扫描与动态点击
            if target_specs and str(target_specs).lower() != 'nan':
                # 兼容三大平台 (JD, TB新老版, 1688新老版)
                sku_selectors = [
                    '.specification-item-sku', '.valueItem--smR4pNt4', 
                    '.skuItem--Z2AJB9Ew .valueItem', '.expand-view-item', 
                    '.sku-item', '.prop-item'
                ]
                
                spec_buttons = []
                for sel in sku_selectors:
                    eles = self.tab.eles(f'css:{sel}')
                    if eles: spec_buttons.extend(eles)
                
                clicked = False
                target_keywords = [k for k in str(target_specs).replace(';',' ').replace(',',' ').split() if len(k)>1]
                
                for btn in spec_buttons:
                    btn_text = btn.text.strip() if btn.text else ""
                    if not btn_text: continue
                    
                    if any(k.upper() in btn_text.upper() for k in target_keywords):
                        try:
                            btn.click(by_js=True)
                            logger.info(f"      🎯 [击破伪装] 成功点击匹配型号: {btn_text}")
                            clicked = True
                            time.sleep(random.uniform(2.0, 3.5)) # 等待价格刷新
                            break
                        except Exception as e:
                            pass
                
                if not clicked:
                    logger.warning(f"      ⚠️ 未能找到完全匹配的规格按钮，默认截取当前显示。")

            # 深度滚动，触发“懒加载”图片
            logger.info("      正在向下滚动加载详情长图...")
            for _ in range(random.randint(4, 7)):
                self.tab.scroll.down(random.randint(600, 1000))
                time.sleep(random.uniform(0.5, 1.2))
            
            self.tab.scroll.up(random.randint(1000, 2000))
            time.sleep(1)

            # 提取真实价格与参数表
            price_selectors = ['.summary-price', '.priceInt--', '.price-info', '.priceWrap--R3TrPIS6', '.od-price-container']
            real_price = "未提取到实时价格"
            for ps in price_selectors:
                price_ele = self.tab.ele(f'css:{ps}', timeout=0.5)
                if price_ele:
                    real_price = price_ele.text.replace('\n', '')
                    break
            
            param_selectors = ['.p-parameter', '.attributes-list', '.offer-attr-list', '.ant-descriptions-view', '#productAttributes']
            spec_text = "未提取到格式化参数表"
            for ps in param_selectors:
                spec_ele = self.tab.ele(f'css:{ps}', timeout=0.5)
                if spec_ele:
                    spec_text = spec_ele.text
                    break

            result_data["text"] = f"【型号选中后实时价格】: {real_price}\n【网页提取参数表】:\n{spec_text}"
            logger.info(f"      ✅ 成功提取文本数据 (当前价格: {real_price})")

            # 智能寻找详情区域并截图
            detail_body = self.tab.ele('#J-detail-content', timeout=0.5) or \
                          self.tab.ele('#description', timeout=0.5) or \
                          self.tab.ele('.html-description', timeout=0.5) or \
                          self.tab.ele('#detail-shadow-vender-top', timeout=0.5) or \
                          self.tab.ele('tag:body', timeout=0.5) 
            
            if detail_body:
                detail_body.get_screenshot(path=image_save_path)
                result_data["image_path"] = image_save_path
                logger.info(f"      📸 详情图已保存至: {image_save_path}")
            
            return result_data
            
        except Exception as e:
            logger.error(f"      ❌ 详情页回采发生异常: {e}")
            return {"text": f"抓取异常: {str(e)}", "image_path": ""}
        finally:
            if self.tab:
                try: self.tab.close()
                except: pass