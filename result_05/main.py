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

# 代理配置：防止请求大模型时误走系统代理
os.environ['NO_PROXY'] = 'localhost,127.0.0.1,0.0.0.0'
for key in ['HTTP_PROXY', 'HTTPS_PROXY', 'http_proxy', 'https_proxy']:
    if key in os.environ: del os.environ[key]

def process_single_task(brand_id, server_ip):
    """
    【分布式核心】处理单个由 Redis 派发的任务
    不再扫全表，指哪打哪！
    """
    # 1. 拿着 brand_id 去云端查出这一个项目的需求和所有候选商品
    group = fetch_single_task(brand_id)
    if not group: return
    
    pid = group['procurement_id']
    name = group['demand'].get('item_name')
    specs = group['demand'].get('specifications', '')[:30]
    cands = group['candidates']
    
    logger.info(f"▶️ [处理中] ID:{brand_id} | {name} | 规格:{specs} | 候选:{len(cands)}家 | 归属:{server_ip}")
    
    if not cands: 
        logger.warning(f"🚫 ID:{brand_id} 无候选商品，跳过。")
        return

    start_time = time.time()
    try:
        # 2. 完美调用你原生的淘汰赛与高斯选品逻辑
        result = tournament_selection(group['demand'], cands)
        duration = time.time() - start_time
    
        if result and result.get('selected'):
            # 3A. 选品成功，直接写回云端库，带上 server_ip
            save_data = {
                "brand_id": brand_id,
                "server_ip": server_ip, # 👉 带上发起请求的服务器身份
                "procurement_id": pid,
                "item_name": name,
                "specifications": group['demand'].get('specifications', ''),
                "selected_suppliers": result.get('selected', []),
                "reason": result.get('overall_reasoning', ''),
                "model": CLOUD_LLM_CONFIG['model'],
                "status": "completed"
            }
            save_analysis_result(save_data)
            logger.info(f"🏆 处理完成 ({duration:.1f}s)。Top1: ￥{result['selected'][0]['price']}")
        else:
            # 3B. 🚨 触发你的原生流标拦截逻辑
            logger.warning(f"🚫 [流标拦截] ID:{brand_id} - 未能匹配到符合规格的商品！")
            
            ai_reason = result.get('overall_reasoning', '') if isinstance(result, dict) else ''
            fail_reason = f"【风控拦截】{ai_reason}" if ai_reason else "AI未能从候选商品中匹配到符合规格的结果，可能遇到了搜索词偏差或低价陷阱。"
            
            fail_data = {
                "brand_id": brand_id,
                "server_ip": server_ip, # 👉 带上服务器身份
                "procurement_id": pid,
                "item_name": name,
                "specifications": group['demand'].get('specifications', ''),
                "selected_suppliers": [], 
                "reason": fail_reason,
                "model": CLOUD_LLM_CONFIG['model'],
                "status": "failed" # 或者保持 completed，只要前端能识别即可
            }
            save_analysis_result(fail_data)

    except Exception as e:
        logger.critical(f"❌ 严重错误: 处理 ID:{brand_id} 时崩溃: {e}", exc_info=True)


def main():
    logger.info("=== 🚀 智能选品引擎 (全自动 Redis 分布式版) 启动 ===")
    
    init_result_table() # 依然保留表结构初始化检查
    
    # 连接云端 Redis
    try:
        r_client = redis.Redis(**REDIS_CONFIG)
        r_client.ping()
        logger.info("✅ 成功连接至云端 Redis 调度中心！静默挂起等待任务...")
    except Exception as e:
        logger.error(f"❌ Redis 连接失败，请检查配置和公网连通性: {e}")
        sys.exit(1)

    while True:
        try:
            # 👉 极速 0 耗能挂起，等待爬虫 04 节点发来的完工信号
            task_data = r_client.brpop("ai_selection_queue", timeout=0)
            
            if task_data:
                _, task_json = task_data
                signal = json.loads(task_json)
                
                brand_id = signal.get('brand_id')
                server_ip = signal.get('server_ip', 'unknown')
                
                logger.info(f"⚡ [收到信号] 爬虫已交单！立刻启动 AI 选品 (BrandID: {brand_id}, 来源: {server_ip})")
                
                # 收到信号就干活！
                process_single_task(brand_id, server_ip)
                
        except KeyboardInterrupt:
            logger.info("👋 接收到停止指令，程序退出。")
            break
        except Exception as e:
            logger.error(f"⚠️ 主循环异常: {e}")
            time.sleep(5)

if __name__ == "__main__":
    main()