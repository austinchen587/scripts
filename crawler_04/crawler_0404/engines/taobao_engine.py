# engines/taobao_engine.py
import random
import time
import re
import urllib.parse
from engines.base_engine import BaseEngine
from logger_helper import logger

class TaobaoEngine(BaseEngine):
    def search(self, keyword):
        # 1. 初始化标签页 (关键词 'taobao')
        if not self.init_tab('taobao'): return []
        
        # 👉 [埋点 1] 刚切过来，先看一眼
        self.check_and_handle_verification('淘宝')

        # 2. 模拟人工搜索
        if 'taobao.com' not in self.tab.url:
            self.tab.get('https://www.taobao.com/')
            self._human_wait(1, 2)
        
        # 定位搜索框
        input_box = self.tab.ele('#q') or \
                    self.tab.ele('css:.search-combobox-input')
        
        if input_box:
            logger.info(f"⌨️ [TB] 发现搜索框，正在输入: {keyword}")
            input_box.clear()
            input_box.input(keyword)
            self._human_wait(0.5, 1.0)
            
            # 定位搜索按钮
            search_btn = self.tab.ele('css:.btn-search') or \
                         self.tab.ele('text:搜索')
            
            if search_btn:
                try:
                    search_btn.click()
                    logger.info("🖱️ [TB] 点击搜索按钮")
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
            # 备用：URL 跳转
            logger.warning("⚠️ [TB] 未找到搜索框，使用跳转")
            url = f'https://s.taobao.com/search?q={urllib.parse.quote(keyword)}'
            self.tab.get(url)
            self._human_wait(2, 3)

        # 👉 [埋点 2] 搜索后，再次检查是否跳到了验证页
        self.check_and_handle_verification('淘宝')

        all_results = []
        
        # === [保留] 核心修复：优先检测“无结果”标志 ===
        no_result_ele = self.tab.ele('text:没有找到相关的宝贝') or \
                        self.tab.ele('text:没找到与') or \
                        self.tab.ele('css:.nrt') 
        
        if no_result_ele:
            logger.warning(f"⚠️ [TB] 页面提示无搜索结果: {keyword}")
            return [] 

        # --- 智能页数计算 ---
        max_page = 1
        
        try:
            # HTML: <span class="next-pagination-display"><em>1</em>/97</span>
            page_info_ele = self.tab.ele('css:.next-pagination-display') or \
                            self.tab.ele('css:.total-page-count') 
            
            if page_info_ele:
                page_text = page_info_ele.text
                total_match = re.search(r'/(\d+)', page_text)
                if total_match:
                    real_total = int(total_match.group(1))
                    if real_total < max_page:
                        logger.info(f"📉 [TB] 搜索结果仅 {real_total} 页，修正爬取目标: {max_page} -> {real_total} 页")
                        max_page = real_total
                    else:
                        logger.info(f"📄 [TB] 搜索结果共 {real_total} 页，计划爬取 {max_page} 页")
        except Exception as e:
            logger.warning(f"⚠️ [TB] 获取总页数失败: {e}")

        logger.info(f"🎲 [TB] 最终计划爬取: {max_page} 页")

        # --- 循环爬取 ---
        for page in range(1, max_page + 1):
            logger.info(f"📄 [TB] 第 {page}/{max_page} 页...")
            
            self._human_scroll()
            
            # 获取商品卡片
            cards = self.tab.eles('css:a[class*="doubleCardWrapper"]')
            if not cards:
                cards = self.tab.eles('css:.item')

            # 👉 [核心熔断] 如果本页没找到商品，先查是不是验证码！
            if not cards:
                self.check_and_handle_verification('淘宝')
                # 再次尝试获取
                cards = self.tab.eles('css:a[class*="doubleCardWrapper"]')
                if not cards:
                    cards = self.tab.eles('css:.item')

            logger.info(f"🔍 [TB] 第 {page} 页找到 {len(cards)} 个商品")

            # ==================================================
            # 👉 [新增] 在这里插入闲逛逻辑
            self.random_wander(cards)
            # ==================================================

            for card in cards:
                try:
                    # --- 解析字段 (极速模式 timeout=0.1) ---
                    detail_url = card.attr('href') or "N/A"
                    if detail_url.startswith('//'):
                        detail_url = 'https:' + detail_url
                    
                    sku = None
                    id_attr = card.attr('id')
                    if id_attr and 'item_id_' in id_attr:
                        sku = id_attr.replace('item_id_', '')
                    
                    if not sku:
                        sku_match = re.search(r'[?&]id=(\d+)', detail_url)
                        sku = sku_match.group(1) if sku_match else None
                    
                    if not sku: continue

                    title_ele = card.ele('css:div[class*="title--"]', timeout=0.1)
                    title = title_ele.text.strip() if title_ele else "N/A"

                    price_int = card.ele('css:div[class*="priceInt--"]', timeout=0.1)
                    price_float = card.ele('css:div[class*="priceFloat--"]', timeout=0.1)
                    price = "0"
                    if price_int:
                        price = price_int.text
                        if price_float:
                            price += price_float.text

                    shop_ele = card.ele('css:span[class*="shopNameText--"]', timeout=0.1)
                    shop_name = shop_ele.text.strip() if shop_ele else "未知店铺"

                    sales_ele = card.ele('css:div[class*="tradeInfoWrapper"]', timeout=0.1)
                    if not sales_ele:
                        sales_ele = card.ele('css:div[class*="summaryADWrapper"]', timeout=0.1)
                    if not sales_ele:
                        sales_ele = card.ele('css:div[class*="realSales--"]', timeout=0.1)
                        
                    sales = sales_ele.text.strip() if sales_ele else "0"

                    hot_ele = card.ele('css:div[class*="subIconWrapper--"]', timeout=0.1)
                    hot_info = hot_ele.text.strip() if hot_ele else ""

                    all_results.append({
                        'sku': sku,
                        '标题': title,
                        '价格': price,
                        '店铺': shop_name,
                        '销量': sales,
                        '详细链接': detail_url,
                        '评价热度': hot_info,
                        '平台': '淘宝'
                    })

                except Exception:
                    continue
            
            # --- 翻页逻辑 (核心修复) ---
            if page < max_page:
                # [修复] 精准定位 button 标签，包含 .next-next 类
                next_btn = self.tab.ele('css:button.next-pagination-item.next-next') or \
                           self.tab.ele('css:button[class*="next-next"]') or \
                           self.tab.ele('text:下一页')

                if not next_btn:
                    logger.info("🚫 [TB] 未找到下一页按钮，提前结束。")
                    break

                if next_btn.attr('disabled') is not None:
                     logger.info("🚫 [TB] 下一页按钮已禁用，提前结束。")
                     break
                
                self._human_wait(2, 5)
                try:
                    # [修复] 强制使用 JS 点击，解决点不中问题
                    next_btn.click(by_js=True)
                    
                    # 淘宝翻页后URL通常会变 (如 &s=44)，我们等待一下
                    self.tab.wait(3) 
                    
                except Exception as e:
                    logger.error(f"❌ [TB] 翻页点击失败: {e}")
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

    def _human_scroll(self):
        for _ in range(random.randint(3, 5)):
            self.tab.scroll.down(random.randint(500, 800))
            time.sleep(random.uniform(0.5, 1.5)) 
        self.tab.scroll.to_bottom()
        time.sleep(random.uniform(0.5, 1.0))

    def _human_wait(self, min_s, max_s):
        time.sleep(random.uniform(min_s, max_s))

    