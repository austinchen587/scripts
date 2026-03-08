import sys
import os
import requests
import time
from db_manager import init_result_table, save_analysis_result
from data_loader import fetch_procurement_groups
from llm_service import tournament_selection
from sync_analysis_results import AnalysisResultSyncer  # 导入同步类
from config import OLLAMA_CONFIG
from logger import logger
from local_listener import start_listener, local_event
from db_manager import init_result_table, save_analysis_result, mark_skus_for_detail

# 代理配置：防止请求本地 Ollama 时误走系统代理
os.environ['NO_PROXY'] = 'localhost,127.0.0.1,0.0.0.0'
for key in ['HTTP_PROXY', 'HTTPS_PROXY', 'http_proxy', 'https_proxy']:
    if key in os.environ: del os.environ[key]

def check_ollama_status():
    """自检 Ollama 服务状态"""
    base_url = OLLAMA_CONFIG['base_url']
    target_model = OLLAMA_CONFIG['model']
    logger.info("正在自检 Ollama 服务状态...")
    try:
        with requests.Session() as session:
            session.trust_env = False
            resp = session.get(f"{base_url}/api/tags", timeout=3)
        if resp.status_code != 200: 
            logger.error(f"❌ 连接 Ollama 失败: {resp.status_code}")
            return False
            
        models = [m['name'] for m in resp.json().get('models', [])]
        if not any(target_model in m for m in models):
            logger.error(f"❌ 未找到模型 {target_model}")
            return False
        logger.info("✅ Ollama 正常。")
        return True
    except Exception as e:
        logger.error(f"❌ 自检异常: {e}")
        return False

def run_procurement_cycle(syncer):
    """
    单个处理周期逻辑：
    1. 检查待处理数据
    2. 执行 AI 选品
    3. 如果有产出，触发云端同步
    """
    init_result_table() # 初始化/检查本地结果表
    groups = fetch_procurement_groups() # 获取待处理组
    total = len(groups)
    
    if total == 0:
        return False # 信号：本次无数据

    logger.info(f"🚀 发现 {total} 个待处理需求，开始执行...")

    for i, group in enumerate(groups):
        brand_id = group['brand_id']
        pid = group['procurement_id']
        name = group['demand'].get('item_name')
        specs = group['demand'].get('specifications', '')[:30]
        cands = group['candidates']
        
        logger.info(f"[{i+1}/{total}] 处理中 -> ID:{brand_id} | {name} | 规格:{specs}...")
        
        if not cands: 
            logger.warning(f"ID:{brand_id} 无候选商品，跳过。")
            continue

        start_time = time.time()
        try:
            # 执行淘汰赛选品逻辑
            result = tournament_selection(group['demand'], cands)
            duration = time.time() - start_time
            
            # ==========================================================
            # 👉 [必须补上的拦截代码] 拦截挂起信号，通知爬虫！
            # ==========================================================
            if isinstance(result, dict) and result.get('status') == 'need_detail':
                mark_skus_for_detail(pid, result['skus'])
                save_data = {
                    "brand_id": brand_id, "procurement_id": pid, "item_name": name,
                    "specifications": group['demand'].get('specifications', ''),
                    "selected_suppliers": [], "reason": "等待爬虫进入详情页核查真实规格与价格...",
                    "model": OLLAMA_CONFIG['model'], 
                    "status": "waiting_detail" # 挂起状态
                }
                save_analysis_result(save_data)
                continue # 直接跳过当前商品，去处理下一个
            # ==========================================================
            
            if result and result.get('selected'):
                save_data = {
                    "brand_id": brand_id,
                    "procurement_id": pid,
                    "item_name": name,
                    "specifications": group['demand'].get('specifications', ''),
                    "selected_suppliers": result.get('selected', []),
                    "reason": result.get('overall_reasoning', ''),
                    "model": OLLAMA_CONFIG['model'],
                    "status": "completed"  # 明确标记完成
                }
                save_analysis_result(save_data) # 结果保存至本地 DB
                logger.info(f"✅ 处理完成 ({duration:.1f}s)。Top1: ￥{result['selected'][0]['price']}")
            else:
                # 🚨 如果 selected 是空列表，或者 result 解析失败，走到这里
                logger.warning(f"🚫 [流标拦截] ID:{brand_id} - 未能匹配到符合规格的商品！")
                
                # 尝试抓取 AI 留下的“遗言”(淘汰原因)，如果没有就用默认文本
                ai_reason = result.get('overall_reasoning', '') if isinstance(result, dict) else ''
                fail_reason = f"【风控拦截】{ai_reason}" if ai_reason else "AI未能从候选商品中匹配到符合规格的结果，可能遇到了搜索词偏差或低价陷阱。"
                
                fail_data = {
                    "brand_id": brand_id,
                    "procurement_id": pid,
                    "item_name": name,
                    "specifications": group['demand'].get('specifications', ''),
                    "selected_suppliers": [], 
                    "reason": fail_reason, # 👉 这里用上了 AI 给出的人性化理由
                    "model": OLLAMA_CONFIG['model'],
                    "status": "failed"   # 明确标记流标
                }
                save_analysis_result(fail_data)

        except Exception as e:
            logger.critical(f"❌ 严重错误: 处理 ID:{brand_id} 时崩溃: {e}", exc_info=True)

    # 处理完一批后，立即执行一次同步
    logger.info("📤 正在将本轮结果同步至云端...")
    try:
        syncer.run()
    except Exception as e:
        logger.error(f"同步失败: {e}")

    return True # 信号：本次处理了数据

def main():
    logger.info("=== 智能选品引擎 (全自动事件驱动版) 启动 ===")
    if not check_ollama_status(): sys.exit(1)
    
    syncer = AnalysisResultSyncer()
    
    # 启动本地静默监听
    start_listener()
    
    # 状态开关：决定下一次是否跳过休眠
    skip_sleep = True

    while True:
        try:
            if not skip_sleep:
                logger.info(f"☕ 库中暂无新任务，AI 挂起等待爬虫抓取... (兜底巡检: 60分钟)")
                is_woken = local_event.wait(timeout=3600)
                if is_woken:
                    logger.info("🎯 [内网极速响应] 爬虫写入完毕，立即开启 AI 选品！")
                    local_event.clear()
            
            skip_sleep = False
            
            # 执行核心周期
            has_data_processed = run_procurement_cycle(syncer)
            
            if has_data_processed:
                logger.info("📦 本轮任务已处理并同步，跳过休眠连轴转检查下一批...")
                skip_sleep = True
                
        except KeyboardInterrupt:
            logger.info("👋 接收到停止指令，程序正在退出...")
            break
        except Exception as e:
            logger.error(f"⚠️ 循环异常: {e}")
            time.sleep(60)

if __name__ == "__main__":
    main()