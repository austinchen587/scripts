# db_helper.py
import psycopg2
import redis
import json
from psycopg2.extras import RealDictCursor, execute_values
from config import REDIS_CONFIG, DB_CONFIG
from logger_helper import logger

r_client = redis.Redis(**REDIS_CONFIG)

# ==============================================================================
# 1. ⚡ 全局缓存检查 (分布式核心：别人找过了，我就不找了)
# ==============================================================================
def check_global_cache(brand_id):
    """
    检查云端数据库是否已经有任何服务器成功抓取过该项目。
    如果有，返回缓存数据以供复用。
    """
    conn = None
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            sql = """
                SELECT item_name, specifications, selected_suppliers, selection_reason, model_used
                FROM procurement_commodity_result 
                WHERE brand_id = %s AND status = 'completed' 
                LIMIT 1;
            """
            cur.execute(sql, (brand_id,))
            return cur.fetchone()
    except Exception as e:
        logger.error(f"❌ 缓存检查失败: {e}")
        return None
    finally:
        if conn: conn.close()

# ==============================================================================
# 2. 💾 统一结果保存 (取代原本的 save_failed_task)
# 支持 server_ip 隔离，互不干扰
# ==============================================================================
def save_task_result(task_info, status='completed', custom_reason=None):
    """
    统一保存结果。无论是抓取成功、全网无结果，还是被风控拦截 (retry)。
    """
    conn = None
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        brand_id = task_info.get('brand_id')
        server_ip = task_info.get('server_ip', 'unknown') # 接收发起请求的服务器 IP
        item_name = task_info.get('item_name', '未知商品')
        procurement_id = task_info.get('procurement_id', '')
        
        # 智能状态判定
        if status == 'retry':
            reason = "系统提示：遭遇平台风控拦截，已加入重试队列等待重新抓取"
            model = "System_Crawler_Blocked"
        elif status == 'completed':
            reason = custom_reason or "全网寻源成功，数据已同步"
            model = "System_Success"
        else:
            reason = custom_reason or "系统提示：未找到匹配的商品价格，请手工审核"
            model = "System_NoResult"

        # 如果没有传选中的供应商，就造一个占位符
        suppliers = task_info.get('selected_suppliers', [{
            "rank": 0, "sku": "N/A", "shop": "系统自动", "price": 0, "reason": reason, "platform": "SYSTEM"
        }])

        with conn.cursor() as cur:
            # 采用联合主键 (brand_id, server_ip) 进行安全更新
            sql = """
                INSERT INTO procurement_commodity_result 
                (brand_id, server_ip, procurement_id, item_name, specifications, selected_suppliers, selection_reason, model_used, status)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (brand_id, server_ip) 
                DO UPDATE SET 
                    status = EXCLUDED.status,
                    selected_suppliers = EXCLUDED.selected_suppliers,
                    selection_reason = EXCLUDED.selection_reason,
                    model_used = EXCLUDED.model_used,
                    updated_at = CURRENT_TIMESTAMP;
            """
            cur.execute(sql, (
                brand_id, server_ip, procurement_id, item_name,
                task_info.get('spec_text', '自动处理'), 
                json.dumps(suppliers, ensure_ascii=False),
                reason, model, status
            ))
            conn.commit()
            logger.info(f"✅ [结果库] 任务 {item_name} (归属: {server_ip}) 状态已更新为: {status}")

    except Exception as e:
        if conn: conn.rollback()
        logger.error(f"❌ 结果保存失败: {e}")
    finally:
        if conn: conn.close()

# ==============================================================================
# 3. 📦 SKU 数据入库 (共享大池子)
# ==============================================================================
def save_skus_to_db(records):
    """
    爬虫抓到的原始 SKU 数据入库，这些数据对所有服务器共享。
    """
    if not records:
        return
    
    conn = None
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        logger.info(f"--- [SKU库] 准备写入 {len(records)} 条原始数据... ---")
        
        sql = """
            INSERT INTO procurement_commodity_sku 
            (brand_id, procurement_id, sku, platform, title, price, shop_name, sales, detail_url, hot_info, item_name)
            VALUES %s
            ON CONFLICT (procurement_id, title, platform) 
            DO UPDATE SET 
                price = EXCLUDED.price,
                sales = EXCLUDED.sales,
                updated_at = CURRENT_TIMESTAMP,
                brand_id = EXCLUDED.brand_id;
        """
        
        with conn.cursor() as cur:
            data = [(
                r.get('brand_id'), r['procurement_id'], r['sku'], r['platform'], r['title'],
                r['price'], r['shop_name'], r['sales'], r['detail_url'], r['hot_info'],
                r['item_name']
            ) for r in records]
            execute_values(cur, sql, data)
            conn.commit()
            logger.info(f"--- [SKU库] {len(records)} 条数据同步成功! ---")
            
    except Exception as e:
        if conn: conn.rollback()
        logger.error(f"--- [SKU库] 写入失败: {e} ---")
    finally:
        if conn: conn.close()

# ==============================================================================
# 4. 🚀 完工发信器
# ==============================================================================
def clear_retry_placeholder(brand_id, server_ip=None):
    """
    抓取完毕后，发送信号给 05_AI_节点，让它开始选品。
    """
    if not brand_id: return
    r_client.lpush("ai_selection_queue", json.dumps({"brand_id": brand_id, "server_ip": server_ip}))
    logger.info(f"🚀 [派发] AI 选品指令已推送至云端 (BrandID: {brand_id}, ServerIP: {server_ip})")

# 【注】删除了 get_pending_tasks，因为现在靠 main.py 去 Redis 抢单了。