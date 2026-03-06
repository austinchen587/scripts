# D:\code\project\scripts\20251227\20260109_step_1\run_full_classification_improved.py
"""
改进版：增强重复检查的增量分类脚本
"""

import sys
import io
import time
from pathlib import Path
import json
from datetime import datetime, timedelta
import traceback

# 强制标准输出使用 UTF-8
if sys.stdout.encoding != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
if sys.stderr.encoding != 'utf-8':
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

# 设置路径
current_dir = Path(__file__).parent
classifier_dir = current_dir.parent / "project\scripts\20251227\20260109_step_1"
if str(classifier_dir) not in sys.path:
    sys.path.insert(0, str(classifier_dir))

from main_classifier import EnhancedProcurementClassifier


class EnhancedDeduplicationClassifier:
    """增强去重分类器"""
    
    def __init__(self):
        self.classifier = EnhancedProcurementClassifier()
        self.already_processed_ids = set()
        self.recently_processed_log = None
        
    def initialize_processed_ids(self):
        """初始化已处理的ID集合"""
        conn = self.classifier.db.get_connection()
        if not conn:
            print("[警告] 无法连接数据库查询已处理记录")
            return
        
        try:
            with conn.cursor() as cur:
                # 查询最近24小时内处理的记录
                cur.execute("""
                    SELECT record_id, updated_at 
                    FROM procurement_emall_category 
                    WHERE updated_at > NOW() - INTERVAL '24 hours'
                    ORDER BY updated_at DESC
                """)
                recent_records = cur.fetchall()
                
                # 查询所有已处理的记录ID
                cur.execute("SELECT record_id FROM procurement_emall_category")
                all_records = cur.fetchall()
                
                self.already_processed_ids = {r[0] for r in all_records}
                print(f"[初始化] 已加载 {len(self.already_processed_ids)} 个已处理ID到内存")
                
                if recent_records:
                    latest_time = recent_records[0][1]
                    recent_count = len(recent_records)
                    print(f"[信息] 最近24小时处理了 {recent_count} 条记录")
                    print(f"[信息] 最新处理时间: {latest_time}")
                    
        except Exception as e:
            print(f"[错误] 初始化已处理ID失败: {e}")
        finally:
            conn.close()
    
    def check_and_record_processing(self, record_id):
        """检查记录是否已处理，并记录当前处理"""
        if record_id in self.already_processed_ids:
            print(f"[跳过] 记录 {record_id} 已在之前处理过，跳过分类")
            return False
        
        # 记录正在处理（防止并发重复处理）
        self.already_processed_ids.add(record_id)
        
        # 可以写入临时日志，防止进程崩溃导致状态丢失
        self._log_processing_start(record_id)
        
        return True
    
    def _log_processing_start(self, record_id):
        """记录处理开始（简单内存日志）"""
        if not hasattr(self, 'processing_log'):
            self.processing_log = []
        
        log_entry = {
            'record_id': record_id,
            'start_time': datetime.now().isoformat(),
            'status': 'processing'
        }
        self.processing_log.append(log_entry)
        
        # 保持日志大小可控
        if len(self.processing_log) > 100:
            self.processing_log = self.processing_log[-50:]
    
    def fetch_uncategorized_records_with_deduplication(self, hours=None):
        """
        获取未分类记录，并进行更严格的去重检查
        
        Args:
            hours: 如果指定，只获取最近N小时的记录
        """
        conn = self.classifier.db.get_connection()
        if not conn:
            raise Exception("无法连接数据库")
        
        try:
            with conn.cursor() as cur:
                if hours:
                    # 只获取最近N小时的新记录
                    cur.execute("""
                        SELECT 
                            e.id,
                            e.project_name,
                            COALESCE(e.commodity_names, ARRAY[]::text[]) AS commodity_names,
                            e.created_at
                        FROM procurement_emall e
                        LEFT JOIN procurement_emall_category c ON e.id = c.record_id
                        WHERE c.record_id IS NULL
                          AND e.project_name IS NOT NULL
                          AND TRIM(e.project_name) != ''
                          AND e.created_at > NOW() - INTERVAL '%s hours'
                        ORDER BY e.id;
                    """, (hours,))
                else:
                    # 获取所有未分类记录
                    cur.execute("""
                        SELECT 
                            e.id,
                            e.project_name,
                            COALESCE(e.commodity_names, ARRAY[]::text[]) AS commodity_names,
                            e.created_at
                        FROM procurement_emall e
                        LEFT JOIN procurement_emall_category c ON e.id = c.record_id
                        WHERE c.record_id IS NULL
                          AND e.project_name IS NOT NULL
                          AND TRIM(e.project_name) != ''
                        ORDER BY e.id;
                    """)
                
                rows = cur.fetchall()
                records = []
                
                for row in rows:
                    record_id = row[0]
                    
                    # 检查是否已在内存中被处理过（防止重复）
                    if self.check_and_record_processing(record_id):
                        records.append({
                            'id': record_id,
                            'project_name': row[1],
                            'commodity_names': row[2],
                            'created_at': row[3]
                        })
                
                return records
        finally:
            conn.close()
    
    def save_results_with_verification(self, results):
        """
        保存结果，并验证是否成功保存
        """
        if not results:
            print("[提示] 无结果需要保存")
            return True
        
        conn = self.classifier.db.get_connection()
        if not conn:
            print("[错误] 无法连接数据库保存结果")
            return False
        
        success_count = 0
        failed_records = []
        
        try:
            with conn.cursor() as cur:
                insert_query = """
                    INSERT INTO procurement_emall_category (
                        record_id, project_name, category, confidence,
                        stage_used, decision_chain, requires_verification, updated_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (record_id) DO UPDATE SET
                        project_name = EXCLUDED.project_name,
                        category = EXCLUDED.category,
                        confidence = EXCLUDED.confidence,
                        stage_used = EXCLUDED.stage_used,
                        decision_chain = EXCLUDED.decision_chain,
                        requires_verification = EXCLUDED.requires_verification,
                        updated_at = EXCLUDED.updated_at
                    RETURNING record_id;
                """
                
                for res in results:
                    try:
                        chain_json = json.dumps(res["decision_chain"], ensure_ascii=False)
                        cur.execute(
                            insert_query,
                            (
                                res["record_id"],
                                res["project_name"],
                                res["category"],
                                float(res["confidence"]),
                                int(res["stage_used"]),
                                chain_json,
                                bool(res["requires_verification"]),
                                datetime.now()
                            )
                        )
                        saved_id = cur.fetchone()[0]
                        success_count += 1
                      #  print(f"  ✓ 已保存记录 {saved_id}")
                        
                    except Exception as e:
                        print(f"  ✗ 保存记录 {res['record_id']} 失败: {e}")
                        failed_records.append({
                            'record_id': res['record_id'],
                            'error': str(e)
                        })
                
                conn.commit()
                if success_count > 0:
                    print(f"  ✓ 本批次成功保存 {success_count} 条记录")
                print(f"\n[详细结果] 成功保存 {success_count}/{len(results)} 条记录")
                
                if failed_records:
                    print(f"[警告] {len(failed_records)} 条记录保存失败:")
                    for fr in failed_records:
                        print(f"  - ID {fr['record_id']}: {fr['error']}")
                    
                    # 将失败记录保存到文件以备后续处理
                    self._save_failed_records(failed_records)
                
                return success_count > 0
                
        except Exception as e:
            conn.rollback()
            print(f"[错误] 批量保存失败: {e}")
            return False
        finally:
            conn.close()
    
    def _save_failed_records(self, failed_records):
        """保存失败记录到日志文件"""
        log_dir = current_dir / "logs" / "failed_records"
        log_dir.mkdir(parents=True, exist_ok=True)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        log_file = log_dir / f"failed_{timestamp}.json"
        
        with open(log_file, 'w', encoding='utf-8') as f:
            json.dump({
                'timestamp': datetime.now().isoformat(),
                'failed_count': len(failed_records),
                'records': failed_records
            }, f, ensure_ascii=False, indent=2)
        
        print(f"[信息] 失败记录已保存到: {log_file}")
    
    def cleanup_incomplete_records(self):
        """
        清理处理失败或中断的记录
        （例如：进程崩溃导致分类未完成）
        """
        conn = self.classifier.db.get_connection()
        if not conn:
            return
        
        try:
            with conn.cursor() as cur:
                # 查找分类质量较差的记录（可能需要重分类）
                cur.execute("""
                    SELECT record_id, confidence, updated_at
                    FROM procurement_emall_category
                    WHERE confidence < 0.5 
                      AND updated_at < NOW() - INTERVAL '1 hour'
                    ORDER BY confidence;
                """)
                low_confidence = cur.fetchall()
                
                if low_confidence:
                    print(f"[清理] 发现 {len(low_confidence)} 条置信度<0.5的旧记录")
                    # 可以选择删除这些记录以便重新分类
                    for rec in low_confidence:
                        print(f"  - ID {rec[0]}: 置信度 {rec[1]}, 更新时间 {rec[2]}")
                
                # 查找潜在重复（同一个记录有多个分类结果）
                cur.execute("""
                    SELECT record_id, COUNT(*) as count
                    FROM procurement_emall_category
                    GROUP BY record_id
                    HAVING COUNT(*) > 1
                    ORDER BY record_id;
                """)
                duplicates = cur.fetchall()
                
                if duplicates:
                    print(f"[警告] 发现 {len(duplicates)} 个重复分类记录:")
                    for dup in duplicates:
                        print(f"  - ID {dup[0]}: {dup[1]} 个分类结果")
        
        finally:
            conn.close()


def main():
    print("=" * 60)
    print("增强版增量分类系统（带严格去重）")
    print("=" * 60)
    
    # 创建增强分类器
    edc = EnhancedDeduplicationClassifier()
    
    # 初始化已处理ID缓存
    print("\n🔄 初始化已处理记录缓存...")
    edc.initialize_processed_ids()
    
    # 选项：只处理最近的记录（减少重复可能性）
    recent_hours = input("\n只处理最近多少小时的新记录？（留空处理所有未分类记录）: ").strip()
    
    try:
        if recent_hours and recent_hours.isdigit():
            hours = int(recent_hours)
            print(f"📊 只处理最近 {hours} 小时的新记录...")
            uncategorized = edc.fetch_uncategorized_records_with_deduplication(hours=hours)
        else:
            print("📊 处理所有未分类记录...")
            uncategorized = edc.fetch_uncategorized_records_with_deduplication()
        
        print(f"[成功] 找到 {len(uncategorized)} 条需要分类的记录")
        
        if not uncategorized:
            print("[完成] 没有需要分类的记录")
            return
        
        # 批次处理（分批提交到数据库，减少风险）
        batch_size = 50
        total_results = []
        
        for i in range(0, len(uncategorized), batch_size):
            batch = uncategorized[i:i+batch_size]
            print(f"\n📦 处理批次 {i//batch_size + 1}/{(len(uncategorized)+batch_size-1)//batch_size}")
            print(f"  本批次: {len(batch)} 条记录 (ID范围: {batch[0]['id']} ~ {batch[-1]['id']})")
            
            # 分类当前批次
            batch_results = []
            for record in batch:
                try:
                    result = edc.classifier.classify_procurement_record(record)
                    if result:
                        batch_results.append(result)
                except Exception as e:
                    print(f"[错误] 分类记录 {record['id']} 失败: {e}")
                    batch_results.append({
                        "record_id": record['id'],
                        "project_name": record.get('project_name', ''),
                        "category": "unknown",
                        "confidence": 0.0,
                        "stage_used": 0,
                        "decision_chain": [f"分类失败: {str(e)[:50]}"],
                        "requires_verification": True
                    })
            
            # 立即保存当前批次
            if batch_results:
                print(f"  正在保存本批次 {len(batch_results)} 个结果...")
                edc.save_results_with_verification(batch_results)
                total_results.extend(batch_results)
            
            # 可选：批次间暂停，避免数据库压力过大
            if i + batch_size < len(uncategorized):
                time.sleep(1)  # 1秒暂停
        
        # 生成统计报告
        print("\n" + "=" * 60)
        print("🎉 分类完成！")
        
        stats = edc.classifier.get_statistics()
        auto_classified = stats["high_confidence"] + stats["medium_confidence"]
        total = stats["total_records"]
        
        if total > 0:
            success_rate = auto_classified / total * 100
            print(f"""
📊 分类统计：
  总处理记录: {total}
  高置信度: {stats['high_confidence']} ({stats['high_confidence_pct']})
  中置信度: {stats['medium_confidence']} ({stats['medium_confidence_pct']})
  低置信度: {stats['low_confidence']} ({stats['low_confidence_pct']})
  自动分类成功率: {success_rate:.1f}%
  强制分类数量: {stats.get('post_processed', 0)}
            """)
        
        # 保存详细日志
        log_dir = current_dir / "logs"
        log_dir.mkdir(exist_ok=True)
        edc.classifier.logger.save_logs()
        
        print(f"\n📝 详细日志已保存至: {log_dir}")
        
        # 可选：运行清理检查
        print("\n🧹 运行清理检查...")
        edc.cleanup_incomplete_records()
        
    except Exception as e:
        print(f"\n❌ 分类过程发生严重错误: {e}")
        print(traceback.format_exc())


if __name__ == "__main__":
    main()
