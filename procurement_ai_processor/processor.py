import logging
import time
from typing import List, Dict, Any
from config import APP_CONFIG
from database import DatabaseManager
from ollama_handler import OllamaHandler
from concurrent.futures import ThreadPoolExecutor, as_completed

logger = logging.getLogger(__name__)

class BrandProcessor:
    def __init__(self):
        self.db = DatabaseManager()
        self.ollama = OllamaHandler()
        self.batch_size = APP_CONFIG["batch_size"]
        self.max_retries = APP_CONFIG["max_retries"]
        self.processed_count = 0
        # [修改点 1] 存储结构变更为集合，存 (id, name)
        self.existing_items = set()
    
    def load_existing_items(self):
        """[修改点 2] 加载已处理的 (ID, 商品名) 组合"""
        logger.info("正在加载已处理的商品记录...")
        self.existing_items = self.db.check_existing_items()
        logger.info(f"✅ 已加载 {len(self.existing_items)} 条历史记录")

    def filter_new_items(self, source_data: List[Dict]) -> List[Dict]:
        """[修改点 3] 基于 ID+商品名 进行精准过滤"""
        new_items = []
        skipped_count = 0
        
        for item in source_data:
            # 组合键：(采购ID, 商品名称)
            check_key = (item.get('procurement_id'), item.get('item_name'))
            
            if check_key in self.existing_items:
                skipped_count += 1
            else:
                new_items.append(item)
        
        logger.info(f"过滤完成: 发现 {len(new_items)} 个新商品，跳过 {skipped_count} 个已处理商品")
        return new_items
    
    def retry_call(self, func, *args, **kwargs):
        for attempt in range(self.max_retries):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                if attempt == self.max_retries - 1: raise
                time.sleep(2 ** attempt)
    
    def process_batch(self, batch: List[Dict]) -> int:
        results_to_insert = []
        print(f"\n{'─' * 60}")
        print(f"📦 处理批次: {len(batch)} 条 (🚀 已开启多线程并发加速)")
        
        # 1. 定义单条数据的处理逻辑（相当于流水线上的单个工人）
        def worker(index, item):
            try:
                quantity = item.get('quantity')
                result = self.retry_call(
                    self.ollama.process_commodity,
                    item_name=item['item_name'],
                    suggested_brand=item['suggested_brand'],
                    specifications=item['specifications'],
                    quantity=quantity
                )
                
                key_word = ""
                platform = ""
                
                if result.get('is_product'):
                    key_word = result.get('key_word', '') or result.get('commodity_summary', item['item_name'])
                    platform = result.get('search_platform', '未知')
                
                if not key_word: return None
                
                print(f"  [并发-{index}] {item['item_name'][:10]}... -> 🔍 {key_word[:20]:<20} | 🛒 {platform}")

                item_to_save = item.copy()
                item_to_save['key_word'] = key_word
                item_to_save['search_platform'] = platform
                return item_to_save
                
            except Exception as e:
                logger.error(f"处理出错 (ID: {item.get('procurement_id')}): {e}")
                print(f"  ❌ [并发-{index}] {item['item_name'][:10]}... 处理失败: {e}")
                return None

        # 2. 启动线程池进行并发请求！
        # ⚠️ 这里的 max_workers 就是并发数，建议设为 5~10
        with ThreadPoolExecutor(max_workers=5) as executor:
            # 将任务分配给线程池
            futures = [executor.submit(worker, i, item) for i, item in enumerate(batch, 1)]
            
            # 收集每个线程的处理结果
            for future in as_completed(futures):
                res = future.result()
                if res:
                    results_to_insert.append(res)
        
        # 3. 收集完并发结果后，依然是一次性批量存入数据库（保护数据库连接）
        if results_to_insert:
            try:
                print(f"  💾 正在批量保存 {len(results_to_insert)} 条...")
                count = self.retry_call(self.db.batch_insert_brand_data, results_to_insert)
                self.processed_count += count
                for res in results_to_insert:
                    self.existing_items.add((res['procurement_id'], res['item_name']))
                    
                print(f"  ✅ 保存成功")
                return count
            except Exception as e:
                logger.error(f"入库失败: {e}")
                print(f"  ❌ 保存失败: {e}")
                return 0
        return 0
    
    def process_all(self):
        print("="*60)
        print("🚀 采购分析引擎 v2.1 (修复多商品漏处理Bug)")
        print("="*60)
        
        # [修改点 4] 调用新加载方法
        self.load_existing_items()
        
        try:
            source_data = self.db.get_source_data()
        except Exception as e:
            logger.error(f"读取源数据失败: {e}")
            return

        new_items = self.filter_new_items(source_data)
        
        if not new_items:
            print("✅ 没有新数据需要处理")
            return
            
        print(f"🎯 发现 {len(new_items)} 条待处理数据")
        for i in range(0, len(new_items), self.batch_size):
            self.process_batch(new_items[i:i + self.batch_size])
        
        print(f"\n✨ 全部完成，共处理 {self.processed_count} 条数据")

    def close(self):
        self.db.close_all()