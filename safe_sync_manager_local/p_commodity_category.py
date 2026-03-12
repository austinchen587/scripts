# safe_sync_manager_fixed_v2.py
"""
安全数据库同步工具 - 带连接诊断和超时设置 - 修复版
"""

import psycopg2
from psycopg2.extras import DictCursor
import socket
import subprocess
import time
from datetime import datetime
import sys
import os

# ==============================================
# 配置部分
# ==============================================

# 源数据库（局域网另一台电脑）
SOURCE_DB = {
    "host": "121.41.128.53",
    "port": 5432,
    "database": "austinchen587_db",
    "user": "austinchen587",
    "password": "austinchen587",
    "connect_timeout": 10,  # 添加连接超时（秒）
}

# 目标数据库（本机）
TARGET_DB = {
    "host": "localhost",  # 如果localhost不行，用127.0.0.1
    "port": 5432,
    "database": "austinchen587_db", 
    "user": "austinchen587",
    "password": "austinchen587",
    "connect_timeout": 5,
}

# 只允许同步的表 - 已更新为 procurement_commodity_category
ALLOWED_TABLES = ["procurement_commodity_category"]

# ==============================================
# 网络诊断工具
# ==============================================

def diagnose_network_connection(host, port, timeout=3):
    """诊断网络连接问题"""
    print(f"\n🔍 诊断网络连接: {host}:{port}")
    print("-" * 50)
    
    # 1. 测试IP可达性
    try:
        print(f"1. 测试IP可达性...")
        socket.setdefaulttimeout(timeout)
        socket.gethostbyname(host)
        print(f"   ✅ IP解析成功")
    except socket.gaierror:
        print(f"   ❌ 无法解析主机名: {host}")
        return False
    except Exception as e:
        print(f"   ❌ IP解析失败: {e}")
        return False
    
    # 2. 测试端口连通性
    try:
        print(f"2. 测试端口 {port} 连通性...")
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        result = sock.connect_ex((host, port))
        sock.close()
        
        if result == 0:
            print(f"   ✅ 端口 {port} 可以连接")
        else:
            print(f"   ❌ 端口 {port} 连接失败 (错误码: {result})")
            print(f"     可能原因: 防火墙阻止/服务未运行/端口错误")
            return False
    except Exception as e:
        print(f"   ❌ 端口测试异常: {e}")
        return False
    
    # 3. 测试Windows防火墙（仅Windows）
    if os.name == 'nt':
        print(f"3. 检查Windows防火墙...")
        try:
            result = subprocess.run(
                ['netsh', 'advfirewall', 'firewall', 'show', 'rule', f'name=PostgreSQL'],
                capture_output=True, text=True, timeout=5
            )
            if "PostgreSQL" in result.stdout:
                print(f"   ⚠️  检测到PostgreSQL防火墙规则")
            else:
                print(f"   ⚠️  未找到PostgreSQL防火墙规则，可能被阻止")
        except:
            pass  # 忽略防火墙检查错误
    
    print("-" * 50)
    return True

def test_postgresql_connection(config, label="数据库"):
    """测试PostgreSQL连接"""
    print(f"\n🔗 测试 {label} 连接 ({config['host']}:{config['port']})...")
    
    try:
        # 使用更短的超时
        test_config = config.copy()
        test_config['connect_timeout'] = 5
        
        conn = psycopg2.connect(**test_config)
        
        # 执行简单查询测试
        cursor = conn.cursor()
        cursor.execute("SELECT version();")
        version = cursor.fetchone()[0]
        
        cursor.execute("SELECT current_database();")
        db_name = cursor.fetchone()[0]
        
        cursor.execute("SELECT current_user;")
        user = cursor.fetchone()[0]
        
        print(f"   ✅ 连接成功!")
        print(f"      数据库: {db_name}")
        print(f"      用户: {user}")
        print(f"      PostgreSQL版本: {version.split(',')[0]}")
        
        cursor.close()
        conn.close()
        return True
        
    except psycopg2.OperationalError as e:
        print(f"   ❌ 连接失败: {e}")
        print(f"      可能原因:")
        print(f"      1. 数据库服务未运行")
        print(f"      2. 防火墙阻止")
        print(f"      3. 主机/端口错误")
        print(f"      4. 用户名/密码错误")
        return False
        
    except Exception as e:
        print(f"   ❌ 连接异常: {e}")
        return False

def check_postgresql_service_windows():
    """检查Windows上的PostgreSQL服务状态"""
    if os.name != 'nt':
        return  # 仅Windows
    
    print("\n🛠️  检查PostgreSQL服务状态...")
    try:
        # 方法1: 使用net命令
        result = subprocess.run(
            ['net', 'start'], 
            capture_output=True, text=True, encoding='gbk', timeout=5
        )
        
        if "postgresql" in result.stdout.lower():
            print("   ✅ PostgreSQL服务正在运行")
        else:
            print("   ⚠️  PostgreSQL服务可能未运行")
            print("      请运行: net start postgresql-x64-16")
            
        # 方法2: 使用sc命令获取详细信息
        result = subprocess.run(
            ['sc', 'query', 'postgresql-x64-16'],
            capture_output=True, text=True, encoding='gbk', timeout=5
        )
        if "RUNNING" in result.stdout:
            print("   ✅ PostgreSQL服务状态: 运行中")
        elif "STOPPED" in result.stdout:
            print("   ❌ PostgreSQL服务状态: 已停止")
    except Exception as e:
        print(f"   ⚠️  服务检查失败: {e}")

# ==============================================
# 表结构管理工具 - 修复版
# ==============================================

def get_table_structure(conn, table_name):
    """获取表结构信息"""
    cursor = conn.cursor()
    
    try:
        # 获取列信息
        cursor.execute("""
            SELECT 
                column_name,
                data_type,
                character_maximum_length,
                is_nullable,
                column_default,
                ordinal_position
            FROM information_schema.columns
            WHERE table_name = %s
            ORDER BY ordinal_position
        """, (table_name,))
        
        columns = cursor.fetchall()
        
        # 获取主键信息
        cursor.execute("""
            SELECT 
                kcu.column_name,
                tc.constraint_type
            FROM information_schema.table_constraints tc
            JOIN information_schema.key_column_usage kcu
                ON tc.constraint_name = kcu.constraint_name
                AND tc.table_schema = kcu.table_schema
            WHERE tc.table_name = %s 
                AND tc.constraint_type IN ('PRIMARY KEY', 'UNIQUE')
        """, (table_name,))
        
        constraints = cursor.fetchall()
        
        # 获取序列信息
        cursor.execute("""
            SELECT column_name, column_default
            FROM information_schema.columns
            WHERE table_name = %s 
                AND column_default LIKE 'nextval%%'
        """, (table_name,))
        
        sequences = cursor.fetchall()
        
        return {
            'columns': columns,
            'constraints': constraints,
            'sequences': sequences
        }
        
    finally:
        cursor.close()

def compare_table_structures(src_structure, tgt_structure, table_name):
    """比较两个表的表结构"""
    print(f"\n📊 比较表结构: {table_name}")
    print("-" * 60)
    
    src_columns = {col[0]: col for col in src_structure['columns']}
    tgt_columns = {col[0]: col for col in tgt_structure['columns']}
    
    print(f"源表列数: {len(src_columns)}")
    print(f"目标表列数: {len(tgt_columns)}")
    
    # 找出差异
    src_only = set(src_columns.keys()) - set(tgt_columns.keys())
    tgt_only = set(tgt_columns.keys()) - set(src_columns.keys())
    common = set(src_columns.keys()) & set(tgt_columns.keys())
    
    if src_only:
        print(f"\n⚠️  目标表缺少的列 ({len(src_only)}):")
        for col in sorted(src_only):
            col_info = src_columns[col]
            print(f"  - {col}: {col_info[1]} {'NULL' if col_info[3]=='YES' else 'NOT NULL'}")
            if col in [seq[0] for seq in src_structure['sequences']]:
                print(f"    (有序列默认值)")
    
    if tgt_only:
        print(f"\n⚠️  源表缺少的列 ({len(tgt_only)}):")
        for col in sorted(tgt_only):
            col_info = tgt_columns[col]
            print(f"  - {col}: {col_info[1]} {'NULL' if col_info[3]=='YES' else 'NOT NULL'}")
    
    print(f"\n✅ 共同列数: {len(common)}")
    return {
        'src_only': src_only,
        'tgt_only': tgt_only,
        'common': common,
        'src_columns': src_columns,
        'tgt_columns': tgt_columns,
        'src_sequences': src_structure['sequences']
    }

def fix_table_structure(src_conn, tgt_conn, table_name):
    """修复表结构：自动对齐列，并将主键修正为 procurement_id"""
    print(f"\n🔧 修复表结构: {table_name}")
    
    src_cursor = src_conn.cursor()
    tgt_cursor = tgt_conn.cursor()
    
    try:
        tgt_conn.rollback()
        
        # ==========================================
        # 1. 修复缺失的列 (保持原有逻辑)
        # ==========================================
        src_structure = get_table_structure(src_conn, table_name)
        tgt_structure = get_table_structure(tgt_conn, table_name)
        diff = compare_table_structures(src_structure, tgt_structure, table_name)
        
        if diff['src_only']:
            for col_name in sorted(diff['src_only']):
                col_info = diff['src_columns'][col_name]
                col_name, data_type, max_length, is_nullable, default_val, _ = col_info
                
                print(f"    ➕ 添加缺失列: {col_name}")
                
                # 处理序列
                is_sequence_col = any(col_name == seq[0] for seq in diff['src_sequences'])
                if is_sequence_col:
                    seq_name = f"{table_name}_{col_name}_seq"
                    try:
                        tgt_cursor.execute(f"CREATE SEQUENCE IF NOT EXISTS {seq_name}")
                        tgt_conn.commit()
                    except:
                        tgt_conn.rollback()

                type_def = f"{data_type}({max_length})" if max_length else data_type
                try:
                    tgt_cursor.execute(f"ALTER TABLE {table_name} ADD COLUMN {col_name} {type_def} NULL")
                    tgt_conn.commit()
                    print(f"      ✅ 列 {col_name} 添加成功")
                except Exception as e:
                    print(f"      ❌ 列 {col_name} 添加失败: {e}")
                    tgt_conn.rollback()

        # ==========================================
        # 2. 深度修复主键 (针对 procurement_id)
        # ==========================================
        target_pk_col = 'procurement_id'  # ✅ 用户指定真正的主键
        
        print(f"  🔍 检查主键一致性 (期望主键: {target_pk_col})...")
        
        # 获取目标表当前真正的主键列
        tgt_cursor.execute("""
            SELECT tc.constraint_name, kcu.column_name
            FROM information_schema.table_constraints tc
            JOIN information_schema.key_column_usage kcu
              ON tc.constraint_name = kcu.constraint_name
              AND tc.table_schema = kcu.table_schema
            WHERE tc.table_name = %s
              AND tc.constraint_type = 'PRIMARY KEY'
        """, (table_name,))
        pk_rows = tgt_cursor.fetchall()
        
        current_pk_name = pk_rows[0][0] if pk_rows else None
        current_pk_cols = sorted([row[1] for row in pk_rows])
        
        # 判断是否需要修复
        needs_fix = False
        if not current_pk_name:
            print(f"    ⚠️  当前无主键")
            needs_fix = True
        elif current_pk_cols != [target_pk_col]:
            print(f"    ⚠️  主键不匹配! 当前: {current_pk_cols}, 期望: ['{target_pk_col}']")
            needs_fix = True
        else:
            print(f"    ✅ 主键配置正确 ({target_pk_col})")
            
        if needs_fix:
            print(f"    🛠️  开始修复主键为 {target_pk_col}...")
            try:
                # A. 如果有旧的主键，先删除
                if current_pk_name:
                    print(f"      - 删除旧主键约束 ({current_pk_name})...")
                    tgt_cursor.execute(f"ALTER TABLE {table_name} DROP CONSTRAINT {current_pk_name}")
                
                # B. 清理 procurement_id 重复数据 (保留最新的一条)
                print(f"      - 检查并清理 {target_pk_col} 重复记录...")
                # 逻辑：对于相同的 procurement_id，保留 ctid 最大（最新写入）的那条
                tgt_cursor.execute(f"""
                    DELETE FROM {table_name} a USING {table_name} b
                    WHERE a.{target_pk_col} = b.{target_pk_col} AND a.ctid < b.ctid
                """)
                del_count = tgt_cursor.rowcount
                if del_count > 0:
                    print(f"        🗑️  已清理 {del_count} 条重复记录")
                
                # C. 创建新主键
                print(f"      - 将 {target_pk_col} 设为新主键...")
                tgt_cursor.execute(f"ALTER TABLE {table_name} ADD PRIMARY KEY ({target_pk_col})")
                tgt_conn.commit()
                print(f"      ✅ 主键修复完成！")
                
            except Exception as e:
                tgt_conn.rollback()
                print(f"      ❌ 主键修复失败: {e}")
                print(f"      (如果不修复主键，后续 Upsert 同步将无法执行)")

        return True

    except Exception as e:
        print(f"  ❌ 结构修复流程异常: {e}")
        tgt_conn.rollback()
        return False
    finally:
        src_cursor.close()
        tgt_cursor.close()

# ==============================================
# 数据库连接管理器（带超时和重试）
# ==============================================

class SafeConnection:
    """带超时和重试的安全连接"""
    
    def __init__(self, config, label="数据库", max_retries=3):
        self.config = config
        self.label = label
        self.max_retries = max_retries
        self.conn = None
        self.cursor = None
    
    def __enter__(self):
        for attempt in range(1, self.max_retries + 1):
            try:
                print(f"\n第 {attempt} 次尝试连接 {self.label}...")
                
                # 先诊断网络
                if not diagnose_network_connection(self.config['host'], self.config['port']):
                    if attempt < self.max_retries:
                        print(f"等待 2 秒后重试...")
                        time.sleep(2)
                        continue
                    else:
                        raise ConnectionError(f"无法连接到 {self.config['host']}:{self.config['port']}")
                
                # 尝试连接数据库
                print(f"建立数据库连接...")
                self.conn = psycopg2.connect(**self.config, cursor_factory=DictCursor)
                self.cursor = self.conn.cursor()
                
                # 测试连接
                self.cursor.execute("SELECT 1")
                print(f"✅ {self.label} 连接成功!")
                return self.conn, self.cursor
                
            except psycopg2.OperationalError as e:
                print(f"❌ 连接失败 (尝试 {attempt}/{self.max_retries}): {e}")
                
                if attempt < self.max_retries:
                    wait_time = attempt * 2
                    print(f"等待 {wait_time} 秒后重试...")
                    time.sleep(wait_time)
                else:
                    raise ConnectionError(f"连接 {self.label} 失败: {e}")
                    
            except Exception as e:
                print(f"❌ 连接异常: {e}")
                raise
        
        raise ConnectionError(f"连接 {self.label} 失败，已达最大重试次数")
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.cursor:
            self.cursor.close()
        if self.conn:
            self.conn.close()

# ==============================================
# 数据同步核心功能 - 修复版
# ==============================================

def sync_table_data_safe(src_conn, tgt_conn, table_name):
    """增量同步表数据：基于 procurement_id 进行 Upsert"""
    print(f"\n📥 增量同步表数据: {table_name}")
    
    src_cursor = src_conn.cursor()
    tgt_cursor = tgt_conn.cursor()
    
    try:
        tgt_conn.rollback()
        
        # 1. 获取列信息
        src_cursor.execute("""
            SELECT column_name FROM information_schema.columns 
            WHERE table_name = %s ORDER BY ordinal_position
        """, (table_name,))
        src_columns_info = src_cursor.fetchall()
        common_columns = [row[0] for row in src_columns_info]
        
        # 2. 确认冲突键 (Upsert 必须指定)
        # ✅ 这里改为用户指定的 procurement_id
        pk_columns = ['procurement_id'] 
        
        # 检查 procurement_id 是否在列列表中
        if 'procurement_id' not in common_columns:
            print("  ❌ 错误: 表中找不到 procurement_id 列，无法同步")
            return False

        # 更新列表排除主键 (虽然主键通常不更新，但在 Upsert 中如果是业务主键，确实不需要更新自己)
        update_columns = [col for col in common_columns if col not in pk_columns]

        # 3. 获取源数据
        select_columns = ', '.join(common_columns)
        src_cursor.execute(f"SELECT {select_columns} FROM {table_name}")
        records = src_cursor.fetchall()
        print(f"  源表记录数: {len(records)}")

        if not records:
            print("  ✅ 源表无数据，跳过同步")
            return True

        # 4. 构建 UPSERT SQL
        placeholders = ', '.join(['%s'] * len(common_columns))
        
        # 动态构建更新部分: col1 = EXCLUDED.col1...
        # 注意：如果 id 列存在于 common_columns 中，它现在会被视为普通数据列进行更新
        update_clause = ', '.join([f"{col} = EXCLUDED.{col}" for col in update_columns])
        
        upsert_sql = f"""
            INSERT INTO {table_name} ({', '.join(common_columns)})
            VALUES ({placeholders})
            ON CONFLICT ({', '.join(pk_columns)}) 
            DO UPDATE SET {update_clause}
        """

        # 5. 执行批量同步
        batch_size = 100
        total_synced = 0
        
        import json
        for i in range(0, len(records), batch_size):
            batch = records[i:i + batch_size]
            batch_data = []
            
            for record in batch:
                processed_record = []
                for value in record:
                    if isinstance(value, (dict, list)):
                        processed_record.append(json.dumps(value))
                    else:
                        processed_record.append(value)
                batch_data.append(tuple(processed_record))
            
            try:
                tgt_cursor.executemany(upsert_sql, batch_data)
                tgt_conn.commit()
                total_synced += len(batch)
                print(f"  ✅ 已处理 {total_synced}/{len(records)} 条记录")
            except Exception as e:
                print(f"  ⚠️  批量同步失败，尝试逐条处理: {e}")
                tgt_conn.rollback()
                for record_data in batch_data:
                    try:
                        tgt_cursor.execute(upsert_sql, record_data)
                        tgt_conn.commit()
                    except Exception as single_err:
                        # 尝试找出哪条数据的 ID 出了问题
                        # 为了调试方便，我们打印出第一列和 procurement_id
                        # 假设 procurement_id 是第二列（索引1），这取决于表结构顺序，仅作参考
                        print(f"    ❌ 记录处理失败: {single_err}")
                        tgt_conn.rollback()

        return True
        
    except Exception as e:
        print(f"❌ 增量同步失败: {e}")
        tgt_conn.rollback()
        return False
    finally:
        src_cursor.close()
        tgt_cursor.close()

# ==============================================
# 主程序
# ==============================================

def main():
    print("\n" + "="*70)
    print("         数据库同步工具 - 修复版")
    print("="*70)
    
    # 步骤1: 诊断本机数据库
    print("\n📊 诊断阶段 1: 本机数据库")
    diagnose_network_connection(TARGET_DB['host'], TARGET_DB['port'])
    test_postgresql_connection(TARGET_DB, "本机数据库")
    
    # 检查Windows服务（如果适用）
    if os.name == 'nt':
        check_postgresql_service_windows()
    
    # 步骤2: 诊断远程数据库
    print("\n📊 诊断阶段 2: 远程数据库")
    if not diagnose_network_connection(SOURCE_DB['host'], SOURCE_DB['port']):
        print("\n❌ 网络诊断失败，请检查:")
        print("   1. 远程电脑是否开机")
        print("   2. 远程电脑防火墙设置")
        print("   3. 网络连接是否正常")
        return 1
    
    if not test_postgresql_connection(SOURCE_DB, "远程数据库"):
        print("\n❌ 远程数据库连接失败")
        print("   请确认远程电脑上的PostgreSQL:")
        print("   1. 服务是否运行")
        print("   2. 是否允许远程连接")
        print("   3. 防火墙是否开放5432端口")
        return 1
    
    # 步骤3: 执行同步
    print("\n" + "="*70)
    print("开始同步...")
    
    try:
        with SafeConnection(SOURCE_DB, "源数据库") as (src_conn, src_cursor):
            with SafeConnection(TARGET_DB, "目标数据库") as (tgt_conn, tgt_cursor):
                
                print("\n✅ 两个数据库连接都成功!")
                
                # 同步每个表
                for table_name in ALLOWED_TABLES:
                    print(f"\n{'='*60}")
                    print(f"处理表: {table_name}")
                    print(f"{'='*60}")
                    
                    # 1. 首先修复表结构
                    if not fix_table_structure(src_conn, tgt_conn, table_name):
                        print(f"⚠️  表结构修复可能有问题，但继续尝试数据同步...")
                    
                    # 2. 同步表数据（使用安全版本）
                    if not sync_table_data_safe(src_conn, tgt_conn, table_name):
                        print(f"❌ 数据同步失败，表 {table_name}")
                        # 继续尝试下一个表
                    else:
                        print(f"✅ 表 {table_name} 同步完成!")
                    
                    print(f"{'='*60}")
                
                print("\n🎉 所有表同步完成!")
                
    except ConnectionError as e:
        print(f"\n❌ 连接错误: {e}")
        return 1
    except Exception as e:
        print(f"\n❌ 同步失败: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    print("\n🎉 同步完成!")
    return 0

if __name__ == "__main__":
    try:
        exit_code = main()
        input("\n按回车键退出...")
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\n\n⏹️  用户中断操作")
        sys.exit(130)
