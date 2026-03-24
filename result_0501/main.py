# main.py
import sys
import os
import time
import json
import redis
from db_manager import init_result_table, save_analysis_result
from data_loader import fetch_single_task
from llm_service import tournament_selection
from config import CLOUD_LLM_CONFIG, REDIS_CONFIG
from logger import logger
from llm_service import run_initial_filter, run_final_decision

# 代理配置：防止请求大模型时误走系统代理
os.environ['NO_PROXY'] = 'localhost,127.0.0.1,0.0.0.0'
for key in ['HTTP_PROXY', 'HTTPS_PROXY', 'http_proxy', 'https_proxy']:
    if key in os.environ: del os.environ[key]

def process_filter_task(task, r_client):
    """【第二棒】AI 负责清洗和初筛大名单，输出 Top 5"""
    brand_id = task.get('brand_id')
    server_ip = task.get('server_ip', 'unknown')
    
    group = fetch_single_task(brand_id)
    if not group or not group.get('candidates'):
        logger.warning(f"🚫 ID:{brand_id} 无候选商品，跳过。")
        save_analysis_result({
            "brand_id": brand_id, "server_ip": server_ip, "procurement_id": task['procurement_id'],
            "item_name": task['item_name'], "specifications": "", "selected_suppliers": [], 
            "reason": "未能从搜索结果中解析出有效的候选商品", "model": CLOUD_LLM_CONFIG['model'], "status": "failed"
        })
        return

    pid = group['procurement_id']
    name = group['demand'].get('item_name')
    specs = group['demand'].get('specifications', '')[:30]
    cands = group['candidates']
    
    logger.info(f"▶️ [阶段2: AI初筛] ID:{brand_id} | {name} | 规格:{specs} | 候选:{len(cands)}家")
    
    # 核心调用：跑 AI 初筛大漏斗
    top_5 = run_initial_filter(group['demand'], cands)
    
    if not top_5:
        logger.warning(f"🚫 [流标拦截] ID:{brand_id} - 初筛全军覆没！")
        save_analysis_result({
            "brand_id": brand_id, "server_ip": server_ip, "procurement_id": pid,
            "item_name": name, "specifications": group['demand'].get('specifications', ''),
            "selected_suppliers": [], "reason": "【风控拦截】所有候选商品均被 AI 识别为低价引流或规格严重不符。",
            "model": CLOUD_LLM_CONFIG['model'], "status": "failed" 
        })
        return
        
    # 成功挑出前 5 名，将其放进原任务字典，传给详情爬虫队列
    task['top_5_candidates'] = top_5
    task['demand'] = group['demand']
    task['platform'] = group['platform'] # 确保平台传递正确
    r_client.lpush("crawler_detail_queue", json.dumps(task))
    logger.info(f"🎯 [交棒] 初筛完成，已选出 Top {len(top_5)}，呼叫爬虫去抓这几家的详情！")

def process_final_task(task):
    """【第四棒】AI 读取完整详情规格，进行决选"""
    brand_id = task.get('brand_id')
    server_ip = task.get('server_ip', 'unknown')
    pid = task.get('procurement_id')
    name = task.get('item_name')
    demand = task.get('demand')
    platform = task.get('platform')
    top_5_candidates = task.get('top_5_candidates')
    
    logger.info(f"⚖️ [阶段4: AI终选法庭] ID:{brand_id} | 接收到带详情的 {len(top_5_candidates)} 家商品")
    start_time = time.time()
    
    try:
        result = run_final_decision(demand, top_5_candidates, platform, pid, brand_id)
        duration = time.time() - start_time
        
        if result and result.get('selected'):
            save_data = {
                "brand_id": brand_id, "server_ip": server_ip, "procurement_id": pid,
                "item_name": name, "specifications": demand.get('specifications', ''),
                "selected_suppliers": result.get('selected', []), 
                "reason": result.get('overall_reasoning', ''),
                "model": CLOUD_LLM_CONFIG['model'], "status": "completed"
            }
            save_analysis_result(save_data)
            logger.info(f"🏆 处理完成 ({duration:.1f}s)。Top1: ￥{result['selected'][0]['price']}")
        else:
            logger.warning(f"🚫 [流标拦截] ID:{brand_id} - 终审全军覆没！")
            fail_data = {
                "brand_id": brand_id, "server_ip": server_ip, "procurement_id": pid,
                "item_name": name, "specifications": demand.get('specifications', ''),
                "selected_suppliers": [], 
                "reason": "【风控拦截】" + (result.get('overall_reasoning', '') if isinstance(result, dict) else "详细核对规格后，无一幸存。"),
                "model": CLOUD_LLM_CONFIG['model'], "status": "failed" 
            }
            save_analysis_result(fail_data)
            
    except Exception as e:
        logger.critical(f"❌ 严重错误: 终审 ID:{brand_id} 崩溃: {e}", exc_info=True)


def main():
    logger.info("=== 🚀 智能选品大脑 (分离式 AI 引擎) 启动 ===")
    init_result_table() 
    
    try:
        r_client = redis.Redis(**REDIS_CONFIG)
        r_client.ping()
        logger.info("✅ 成功连接至云端 Redis。监听 [ai_filter_queue] 和 [ai_final_queue]...")
    except Exception as e:
        logger.error(f"❌ Redis 连接失败: {e}")
        sys.exit(1)

    while True:
        try:
            task_data = r_client.blpop(["ai_filter_queue", "ai_final_queue"], timeout=0)
            if task_data:
                queue_name = task_data[0]
                payload = json.loads(task_data[1])
                
                if queue_name == "ai_filter_queue":
                    process_filter_task(payload, r_client)
                elif queue_name == "ai_final_queue":
                    process_final_task(payload)
                    
        except KeyboardInterrupt:
            logger.info("👋 接收到停止指令，程序退出。")
            break
        except Exception as e:
            logger.error(f"⚠️ 主循环异常: {e}")
            time.sleep(5)

if __name__ == "__main__":
    main()