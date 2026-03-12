# engines/s1688_engine.py
import random
import time
import urllib.parse
import re
from engines.base_engine import BaseEngine
from logger_helper import logger

class S1688Engine(BaseEngine):
    def search(self, keyword):
        # 传入平台关键词 '1688'
        if not self.init_tab('1688'): return []
        
        # [熔断检测] 刚切过来，先看一眼
        self.check_and_handle_verification('1688')

        base_url = 'https://s.1688.com/page/pccps.html'
        
        # 确保在搜索页 (包含 s.1688.com 即可，兼容 offer_search.htm)
        if 's.1688.com' not in (self.tab.url or ""):
            self.tab.get(base_url)
            self._human_wait(1, 2)
        
        # 定位搜索框
        input_box = self.tab.ele('#alisearch-input')
        
        if input_box:
            logger.info(f"⌨️ [1688] 发现搜索框，正在输入: {keyword}")
            input_box.clear()
            input_box.input(keyword)
            self._human_wait(0.5, 1)
            
            # 定位搜索按钮
            search_btn = self.tab.ele('css:.input-button') or self.tab.ele('text:搜 索')
            
            if search_btn:
                search_btn.click()
                logger.info("🖱️ [1688] 点击搜索按钮")
            else:
                input_box.input('\n')
            
            try:
                self.tab.wait.doc_loaded()
            except:
                self.tab.wait(3)
            
            self._human_wait(2, 4)
        else:
            # 如果找不到搜索框，使用 URL 跳转兜底
            url = f'{base_url}?keywords={urllib.parse.quote(keyword)}'
            logger.info(f"🌐 [1688] 未找到搜索框，使用跳转: {keyword}")
            self.tab.get(url)
            self._human_wait(2, 4)

        # [熔断检测] 搜索后，再次检查是否跳到了验证页
        self.check_and_handle_verification('1688')

        all_results = []

        # === 核心修复：优先检测“无结果”标志 ===
        no_result_ele = self.tab.ele('text:没有找到关于') or \
                        self.tab.ele('css:.sm-no-result') or \
                        self.tab.ele('text:抱歉，没有找到')
        
        if no_result_ele:
            logger.warning(f"⚠️ [1688] 页面提示无搜索结果: {keyword}")
            return [] 
        
        # --- 智能页数计算 ---
        max_page = 1
        
        try:
            # 增加 timeout 防止获取总页数卡顿
            total_ele = self.tab.ele('css:.fui-paging-num', timeout=2)
            if total_ele:
                total_text = total_ele.text.strip()
                if total_text.isdigit():
                    real_total = int(total_text)
                    if real_total < max_page:
                        logger.info(f"📉 [1688] 搜索结果仅 {real_total} 页，修正爬取目标: {max_page} -> {real_total} 页")
                        max_page = real_total
                    else:
                        logger.info(f"📄 [1688] 搜索结果共 {real_total} 页，计划爬取 {max_page} 页")
        except Exception as e:
            logger.warning(f"⚠️ [1688] 获取总页数失败，将使用默认随机页数: {e}")

        logger.info(f"🎲 [1688] 最终计划爬取: {max_page} 页")

        for page in range(1, max_page + 1):
            # ==============================================================
            # 👉 [关键修复] 严格判定误入详情页
            # 只认 detail.1688.com 域名，绝不检查 'offer' 单词！
            # 这样就完美兼容了 offer_search.htm
            # ==============================================================
            if 'detail.1688.com' in (self.tab.url or ""):
                logger.warning(f"⚠️ [1688] 检测到误入商品详情页，正在执行后退操作...")
                self.tab.back()
                try:
                    self.tab.wait.doc_loaded()
                except:
                    pass
                self._human_wait(2, 3)

            logger.info(f"📄 [1688] 第 {page}/{max_page} 页...")
            
            self._human_scroll()
            
            # 获取商品卡片
            cards = self.tab.eles('css:.search-offer-wrapper')
            if not cards:
                cards = self.tab.eles('xpath://div[contains(@class, "offer-list-row")]//li')

            # [熔断检测] 如果本页没找到商品，先查是不是验证码！
            if not cards:
                self.check_and_handle_verification('1688')
                # 再次尝试获取
                cards = self.tab.eles('css:.search-offer-wrapper')
                if not cards:
                    cards = self.tab.eles('xpath://div[contains(@class, "offer-list-row")]//li')

            logger.info(f"🔍 [1688] 第 {page} 页找到 {len(cards)} 个商品")

            # ==================================================
            # 随机闲逛 (BaseEngine 中的通用功能)
            # ==================================================
            self.random_wander(cards)

            for card in cards:
                try:
                    # --- 解析字段 (全部增加 timeout=0.1 极速模式) ---
                    detail_url = card.attr('href') or "N/A"
                    if not detail_url.startswith('http'):
                        ele_a = card.ele('tag:a', timeout=0.1)
                        detail_url = ele_a.attr('href') if ele_a else "N/A"

                    # 提取 SKU ID (offerId)
                    sku_match = re.search(r'offerId=(\d+)', detail_url)
                    sku = sku_match.group(1) if sku_match else None
                    if not sku: continue

                    title_ele = card.ele('css:.offer-title-row .title-text', timeout=0.1)
                    title = title_ele.text.strip() if title_ele else "N/A"

                    price_ele = card.ele('css:.offer-price-row .price-item .text-main', timeout=0.1)
                    price = price_ele.text.strip() if price_ele else "0"

                    sales_ele = card.ele('css:.offer-price-row .col-desc_after .desc-text', timeout=0.1)
                    sales = sales_ele.text.strip() if sales_ele else "0"

                    shop_ele = card.ele('css:.offer-shop-row .col-left .desc-text', timeout=0.1)
                    shop_name = shop_ele.text.strip() if shop_ele else "未知店铺"

                    hot_ele = card.ele('css:.offer-tag-row .col-desc_after .desc-text', timeout=0.1)
                    hot_info = hot_ele.text.strip() if hot_ele else ""

                    all_results.append({
                        'sku': sku,
                        '标题': title,
                        '价格': price,
                        '店铺': shop_name,
                        '销量': sales,
                        '详细链接': detail_url,
                        '评价热度': hot_info,
                        '平台': '1688'
                    })

                except Exception as e:
                    continue
            
            # --- 翻页逻辑 ---
            if page < max_page:
                next_btn = self.tab.ele('css:.fui-next') or \
                           self.tab.ele('css:.fui-arrow.fui-next') or \
                           self.tab.ele('text:^下一页$') or \
                           self.tab.ele('css:.pagination-next')

                if not next_btn:
                    logger.info("🚫 [1688] 未找到下一页按钮，提前结束。")
                    break
                    
                class_attr = next_btn.attr('class') or ''
                if 'disable' in class_attr:
                    logger.info("🚫 [1688] 下一页按钮已禁用，提前结束。")
                    break
                
                self._human_wait(2, 5)
                try:
                    # 强制使用 JS 点击
                    next_btn.click(by_js=True)
                    self.tab.wait(2) 
                except Exception as e:
                    logger.error(f"❌ [1688] 翻页点击失败: {e}")
                    break
        
        return all_results

    def _human_scroll(self):
        for _ in range(random.randint(4, 6)):
            self.tab.scroll.down(random.randint(600, 900))
            time.sleep(random.uniform(0.8, 1.8)) 
        self.tab.scroll.to_bottom()
        time.sleep(random.uniform(1.0, 2.0))

    def _human_wait(self, min_s, max_s):
        time.sleep(random.uniform(min_s, max_s))

    