# D:\code\project\scripts\know_099\main.py
import logging
import json
import time
from tqdm import tqdm
from db_manager import DBManager
from llm_client import OllamaClient
from graph_engine import GraphEngine
from config import TABLE_SOURCE

# 配置日志：文件记录详细，屏幕只留进度条
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.FileHandler("run.log", encoding='utf-8')]
)
logger = logging.getLogger(__name__)

def main():
    print("=== 启动增量知识图谱构建 (V3.0 Multi-Platform) ===")
    
    db = DBManager()
    db.init_schema()
    
    ollama = OllamaClient()
    engine = GraphEngine(db)
    
    # 1. 获取任务总量
    print("正在计算待处理数据总量...")
    total_pending = db.get_unprocessed_count(TABLE_SOURCE)
    print(f"发现 {total_pending} 条待处理数据。开始作业...")

    BATCH_SIZE = 10
    
    # 2. 初始化全局进度条
    with tqdm(total=total_pending, unit="rec", desc="Graph Building", ncols=120, mininterval=0.5) as pbar:
        try:
            while True:
                # 1. 读取数据 (s.* 会包含 platform 字段)
                records = db.fetch_unprocessed(TABLE_SOURCE, BATCH_SIZE)
                if not records:
                    break

                batch_results = []
                
                # 2. 逐条处理
                for row in records:
                    rid, title = row['id'], row['title']
                    # 注意: row['platform'] 已由数据库直接提供
                    
                    # 简略标题用于展示
                    short_title = (title[:20] + '...') if len(title) > 20 else title

                    try:
                        # AI 提取
                        data = ollama.extract_info(title) if title else {}
                        
                        # 实时展示提取结果 (不打断进度条)
                        if data:
                            tqdm.write(f"[ID:{rid}] {short_title} -> {json.dumps(data, ensure_ascii=False)}")
                        else:
                            tqdm.write(f"[ID:{rid}] {short_title} -> [空结果]")

                        # 构建图谱 (引擎会自动读取 row['platform'])
                        if data: engine.process_record(row, data)
                        
                        # 记录成功
                        batch_results.append((rid, 'success', json.dumps(data, ensure_ascii=False)))
                        
                    except Exception as e:
                        err_msg = str(e)
                        tqdm.write(f"[ID:{rid}] ❌ Error: {err_msg}")
                        logger.error(f"Row {rid} Failed: {err_msg}")
                        batch_results.append((rid, 'error', json.dumps({"err": err_msg})))

                # 3. 提交状态
                db.save_batch_results(batch_results)
                pbar.update(len(records))

        except KeyboardInterrupt:
            tqdm.write("\n任务手动停止")
            logger.warning("任务手动停止")
        finally:
            db.close()
            tqdm.write(f"\n任务结束。详细日志请查看 run.log")

if __name__ == "__main__":
    main()