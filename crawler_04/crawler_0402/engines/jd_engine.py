# engines/jd_engine.py
import random, time, urllib.parse
import re
from engines.base_engine import BaseEngine
from logger_helper import logger

class JDEngine(BaseEngine):
    def search(self, keyword):
        if not self.init_tab('jd'): return []
        
        # 👉 [埋点 1] 刚切过来，先看一眼是不是已经在登录页了
        self.check_and_handle_verification('京东')

        # 1. 模拟人工搜索
        if 'jd.com' not in self.tab.url:
            self.tab.get('https://www.jd.com/')
            self._human_wait(1, 2)

        input_box = self.tab.ele('css:.jd_pc_search_bar_react_search_input') or \
                    self.tab.ele('css:#key')
        
        if input_box:
            logger.info(f"⌨️ [JD] 发现搜索框，正在输入: {keyword}")
            input_box.clear()
            input_box.input(keyword)
            self._human_wait(0.5, 1.0)

            search_btn = self.tab.ele('css:.jd_pc_search_bar_react_search_btn') or \
                         self.tab.ele('css:.button') or \
                         self.tab.ele('text:搜索')
            
            if search_btn:
                try:
                    search_btn.click()
                    logger.info("🖱️ [JD] 点击搜索按钮")
                except:
                    input_box.input('\n')
            else:
                input_box.input('\n')
            
            try:
                self.tab.wait.doc_loaded()
            except:
                self.tab.wait(3)
                
            self._human_wait(2, 4)
        else:
            logger.warning("⚠️ [JD] 未找到搜索框，使用备用跳转")
            url = f'https://search.jd.com/Search?keyword={urllib.parse.quote(keyword)}&enc=utf-8'
            self.tab.get(url)
            self._human_wait(2, 3)

        # 👉 [埋点 2] 搜索后，再次检查是否跳到了验证页
        self.check_and_handle_verification('京东')

        all_results = []
        
        # === [核心修复] 极速无结果检测 ===
        # 1. 检测明确的文字提示 (timeout=1，快速判断)
        no_result_ele = self.tab.ele('text:抱歉，没有找到', timeout=1) or \
                        self.tab.ele('css:.check-error', timeout=1) or \
                        self.tab.ele('text:建议您', timeout=1)
        
        if no_result_ele:
            logger.warning(f"⚠️ [JD] 页面提示无搜索结果: {keyword}")
            return [] # 返回空 -> 触发 main.py 写入占位数据 -> 结束

        # 2. [新增] 兜底：检测是否有商品卡片
        # 如果没看到“抱歉”字样，但页面上确实没有商品卡片，也直接视为无结果
        has_items = self.tab.ele('tag:div@@class:plugin_goodsCardWrapper', timeout=1) or \
                    self.tab.ele('.gl-item', timeout=1)
        
        # 👉 [核心熔断] 如果没找到商品，再做最后一次验证码确认！
        if not has_items:
            # 如果这里由于验证码导致没商品，它会卡住报警
            self.check_and_handle_verification('京东') 
            
            # 如果人工解决完验证码回来（代码继续往下走），再查一次
            has_items = self.tab.ele('tag:div@@class:plugin_goodsCardWrapper', timeout=1) or \
                        self.tab.ele('.gl-item', timeout=1)

            if not has_items:
                logger.warning(f"⚠️ [JD] 未检测到任何商品元素，视为无结果: {keyword}")
                return [] # 返回空 -> 触发 main.py 写入占位数据 -> 结束

        # --- 智能页数计算 ---
        max_page = 1
        
        try:
            total_ele = self.tab.ele('css:._pagination_total_1jczn_61', timeout=2) or \
                        self.tab.ele(r'text:^共\d+页$', timeout=2)
            
            if total_ele:
                total_text = total_ele.text
                num_match = re.search(r'(\d+)', total_text)
                if num_match:
                    real_total = int(num_match.group(1))
                    if real_total < max_page:
                        logger.info(f"📉 [JD] 搜索结果仅 {real_total} 页，修正爬取目标: {max_page} -> {real_total} 页")
                        max_page = real_total
                    else:
                        logger.info(f"📄 [JD] 搜索结果共 {real_total} 页，计划爬取 {max_page} 页")
        except Exception as e:
            logger.warning(f"⚠️ [JD] 获取总页数失败 (默认爬取 {max_page} 页): {e}")

        logger.info(f"🎲 [JD] 最终计划爬取: {max_page} 页")

        for page in range(1, max_page + 1):
            logger.info(f"📄 [JD] 第 {page}/{max_page} 页...")
            
            self._human_scroll()
            
            # 获取商品卡片
            cards = self.tab.eles('tag:div@@class:plugin_goodsCardWrapper')
            if not cards: cards = self.tab.eles('.gl-item')
            
            # [新增] 如果在循环中发现这一页是空的，直接退出
            if not cards:
                logger.info(f"🚫 [JD] 第 {page} 页未找到商品，停止爬取。")
                break

            # ==========================================
            # 👉 [新增] 插入这一行代码即可
            self.random_wander(cards) 
            # ==========================================

            for card in cards:
                try:
                    sku = card.attr('data-sku')
                    if not sku:
                        continue
                        
                    # [核心修复] 全部加上 timeout=1，并且安全取值
                    title_ele = card.ele('xpath:.//span[contains(@class, "text")]', timeout=1) or \
                                card.ele('xpath:.//*[@title]', timeout=1)
                    title = title_ele.attr('title') or title_ele.text if title_ele else "N/A"
                    
                    price_ele = card.ele('xpath:.//*[contains(@class, "price")]', timeout=1)
                    price = price_ele.text.strip() if price_ele else "0"
                    
                    shop_ele = card.ele('xpath:.//*[contains(@class, "name")]', timeout=1)
                    shop = shop_ele.text.strip() if shop_ele else "未知店铺"
                    
                    sales_ele = card.ele('xpath:.//*[contains(@class, "volume")]', timeout=1)
                    sales = sales_ele.text.strip() if sales_ele else "0"
                    
                    hot_ele = card.ele('xpath:.//*[contains(@class, "common-wrap") or contains(@class, "text-list")]', timeout=1)
                    hot_info = hot_ele.text.strip() if hot_ele else ""

                    all_results.append({
                        'sku': sku,
                        '标题': title,
                        '价格': price,
                        '店铺': shop,
                        '销量': sales,
                        '详细链接': f"https://item.jd.com/{sku}.html",
                        '评价热度': hot_info,
                        '平台': '京东'
                    })
                except Exception as e:
                    continue
            
            # --- 翻页逻辑 ---
            if page < max_page:
                next_btn = self.tab.ele('css:._pagination_next_1jczn_8') or \
                           self.tab.ele('css:.pn-next') or \
                           self.tab.ele('title:使用下一页') or \
                           self.tab.ele('text:^下一页$')

                if not next_btn:
                    logger.info("🚫 [JD] 未找到下一页按钮，提前结束。")
                    break

                if 'disabled' in next_btn.attr('class') or 'disable' in next_btn.attr('class'): 
                    logger.info("🚫 [JD] 下一页按钮已禁用，提前结束。")
                    break
                
                self._human_wait(2, 4) 
                try:
                    next_btn.click()
                    self.tab.wait(2)
                except Exception as e:
                    logger.error(f"❌ [JD] 翻页失败: {e}")
                    break
        
        return all_results

    def _human_scroll(self):
        for _ in range(random.randint(3, 5)):
            self.tab.scroll.down(random.randint(500, 800))
            time.sleep(random.uniform(0.5, 1.5)) 
        self.tab.scroll.to_bottom()
        time.sleep(random.uniform(0.5, 1.0))

    def _human_wait(self, min_s, max_s):
        time.sleep(random.uniform(min_s, max_s))