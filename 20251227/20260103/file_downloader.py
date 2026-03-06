# file_downloader.py
import json
import psycopg2
import requests
import os
import logging
from pathlib import Path
from datetime import datetime
from urllib.parse import urlparse
import time
from typing import List, Dict, Optional
from config_downfile import DATABASE_CONFIG, FILE_CONFIG, DOWNLOAD_CONFIG, LOGGING_CONFIG

class GoodsFileDownloader:
    def __init__(self, db_config: Dict = None, file_config: Dict = None, download_config: Dict = None):
        """
        初始化文件下载器
        """
        self.db_config = db_config or DATABASE_CONFIG
        self.file_config = file_config or FILE_CONFIG
        self.download_config = download_config or DOWNLOAD_CONFIG
        
        # 设置路径
        self.base_save_path = Path(self.file_config['base_save_path'])
        self.log_dir = Path(self.file_config['log_dir'])
        
        # 创建目录
        self.base_save_path.mkdir(parents=True, exist_ok=True)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        
        # 设置日志
        self.setup_logging()
        
        # 数据库连接
        self.conn = None
        
    def setup_logging(self):
        """设置日志系统"""
        timestamp = datetime.now().strftime("%Y%m%d_%H时-%M分")
        log_file = self.log_dir / f"file_download_{timestamp}.log"
        
        logging.basicConfig(
            level=getattr(logging, LOGGING_CONFIG['level']),
            format=LOGGING_CONFIG['format'],
            datefmt=LOGGING_CONFIG['date_format'],
            handlers=[
                logging.FileHandler(log_file),
                logging.StreamHandler()
            ]
        )
        self.logger = logging.getLogger(__name__)
        
        self.logger.info(f"日志文件已创建: {log_file}")
        self.logger.info(f"文件保存路径: {self.base_save_path}")
        self.logger.info(f"日志保存路径: {self.log_dir}")
        
    def connect_db(self) -> bool:
        """连接数据库"""
        try:
            self.conn = psycopg2.connect(**self.db_config)
            self.logger.info("✅ 数据库连接成功")
            return True
        except Exception as e:
            self.logger.error(f"❌ 数据库连接失败: {e}")
            return False
            
    def disconnect_db(self):
        """断开数据库连接"""
        if self.conn:
            self.conn.close()
            self.logger.info("✅ 数据库连接已关闭")
            
    def get_record_details(self, record_id: int) -> Optional[Dict]:
        """获取记录的详细信息"""
        try:
            with self.conn.cursor() as cur:
                cur.execute("""
                SELECT 
                    id, project_name, commodity_names, parameter_requirements,
                    purchase_quantities, control_amounts, suggested_brands,
                    business_items, business_requirements, related_links,
                    download_files, purchasing_unit
                FROM procurement_emall 
 WHERE id = %s
                """, (record_id,))
                
                row = cur.fetchone()
                if row:
                    return {
                        'id': row[0],
                        'project_name': row[1],
                        'commodity_names': row[2],
                        'parameter_requirements': row[3],
                        'purchase_quantities': row[4],
                        'control_amounts': row[5],
                        'suggested_brands': row[6],
                        'business_items': row[7],
                        'business_requirements': row[8],
                        'related_links': row[9],
                        'download_files': row[10],
                        'purchasing_unit': row[11]
                    }
                return None
                
        except Exception as e:
            self.logger.error(f"❌ 查询记录 {record_id} 失败: {e}")
            return None
            
    def download_file(self, url: str, save_path: Path) -> bool:
        """下载单个文件（支持重试）"""
        # 先检查URL是否有效
        if not url or not url.strip():
            self.logger.error(f"❌ 空URL，跳过")
            return False
            
        # 检查URL格式
        parsed = urlparse(url)
        if not parsed.scheme or not parsed.netloc:
            self.logger.error(f"❌ 无效的URL格式: {url}")
            return False
            
        for attempt in range(self.download_config['retry_attempts']):
            try:
                headers = {
                    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36'
                }
                
                response = requests.get(
                    url, 
                    headers=headers, 
                    stream=True, 
                    timeout=self.download_config['timeout']
                )
                response.raise_for_status()
                
                # 确保保存目录存在
                save_path.parent.mkdir(parents=True, exist_ok=True)
                
                with open(save_path, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=self.download_config['chunk_size']):
                        f.write(chunk)
                        
                self.logger.info(f"✅ 文件下载成功: {save_path}")
                return True
                
            except requests.exceptions.RequestException as e:
                if attempt < self.download_config['retry_attempts'] - 1:
                    self.logger.warning(f"⚠️ 下载失败，第{attempt + 1}次重试: {url}")
                    time.sleep(self.download_config['retry_delay'])
                else:
                    self.logger.error(f"❌ 下载失败 {url}: {e}")
                    return False
            except Exception as e:
                self.logger.error(f"❌ 下载过程出错 {url}: {e}")
                return False
                
        return False
        
    def has_valid_files(self, record_data: Dict) -> bool:
        """检查记录是否有有效文件需要下载"""
        # 检查 related_links 是否有非空URL
        has_links = False
        if record_data.get('related_links'):
            links = record_data['related_links']
            if isinstance(links, list):
                for url in links:
                    if url and url.strip():
                        parsed = urlparse(url)
                        if parsed.scheme and parsed.netloc:
                            has_links = True
                            break
        
        return has_links
        
    def process_record_files(self, record_data: Dict) -> Dict:
        """处理单个记录的文件下载"""
        record_id = record_data.get('id')
        project_name = record_data.get('project_name', 'Unknown')
        
        if not record_id:
            self.logger.error("❌ 记录缺少id字段")
            return {'errors': ['缺少id'], 'downloaded_files': []}
            
        result = {
            'record_id': record_id,
            'project_name': project_name,
            'downloaded_files': [],
            'errors': []
        }
        
        self.logger.info(f"📁 处理记录 {record_id}: {project_name}")
        
        # 检查是否有有效的文件
        if not self.has_valid_files(record_data):
            self.logger.info(f"ℹ️  记录 {record_id} 无有效文件可下载")
            return result
        
        # 创建记录文件夹
        record_folder = self.base_save_path / str(record_id)
        
        # 下载 related_links
        if record_data.get('related_links'):
            links = record_data['related_links']
            download_files = record_data.get('download_files', [])
            
            if isinstance(links, list):
                for i, url in enumerate(links):
                    if url and url.strip():
                        # 检查URL格式
                        parsed = urlparse(url)
                        if not parsed.scheme or not parsed.netloc:
                            self.logger.warning(f"⚠️ 跳过无效URL: {url}")
                            continue
                            
                        # 获取对应的文件名
                        filename = None
                        if isinstance(download_files, list) and i < len(download_files):
                            filename = download_files[i]
                        
                        if not filename or not filename.strip():
                            # 如果download_files中没有对应文件名，从URL提取
                            filename = os.path.basename(parsed.path)
                            if not filename or '.' not in filename:
                                filename = f"file_{i+1}.bin"
                        
                        save_path = record_folder / filename
                        
                        if self.download_file(url, save_path):
                            result['downloaded_files'].append(str(save_path))
                        else:
                            result['errors'].append(f"文件 {filename}: {url}")
                        
        return result
        
    def process_json_file(self, json_file_path: str = None) -> Dict:
        """处理JSON文件"""
        # 如果未指定JSON文件路径，使用默认路径
        if not json_file_path:
            json_file_path = self.file_config.get('default_json_path')
            if not json_file_path or not os.path.exists(json_file_path):
                self.logger.error("❌ 未指定JSON文件路径且默认路径不存在")
                return {'success': False, 'error': 'JSON文件路径不存在'}
        
        timestamp = datetime.now().strftime("%Y%m%d_%H时-%M分")
        results_file = self.log_dir / f"download_results_{timestamp}.json"
        
        try:
            # 读取JSON文件
            with open(json_file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                
            self.logger.info(f"📄 读取JSON文件: {json_file_path}")
            
            # 检测JSON结构 - 你的JSON文件有results字段
            if isinstance(data, dict) and 'results' in data:
                # 这是你的分类结果格式
                all_records = data['results']
                self.logger.info(f"📊 总记录数: {len(all_records)}")
                
                # 找到所有category为goods的记录
                goods_records = [item for item in all_records if item.get('category') == 'goods']
                self.logger.info(f"🔧 goods类别记录数: {len(goods_records)}")
                
                # 提取record_id列表
                goods_record_ids = [str(record['record_id']) for record in goods_records if record.get('record_id')]
                self.logger.info(f"📋 goods类别record_id列表: {', '.join(goods_record_ids)}")
                
            else:
                self.logger.error("❌ JSON数据格式错误，缺少results字段")
                return {'success': False, 'error': 'JSON数据格式错误'}
            
            if not goods_records:
                self.logger.warning("⚠️ 没有找到goods类别的记录")
                return {'success': True, 'message': '没有找到goods类别的记录'}
            
            # 连接数据库
            if not self.connect_db():
                return {'success': False, 'error': '数据库连接失败'}
            
            results = []
            success_count = 0
            error_count = 0
            no_files_count = 0
            
            for record in goods_records:
                record_id = record.get('record_id')
                if not record_id:
                    self.logger.warning(f"⚠️ 跳过无record_id的记录")
                    continue
                    
                # 从数据库获取详细信息
                db_record = self.get_record_details(record_id)
                if not db_record:
                    self.logger.warning(f"⚠️ 数据库中找不到记录 {record_id}")
                    error_count += 1
                    continue
                    
                # 处理文件下载
                result = self.process_record_files(db_record)
                results.append(result)
                
                if result.get('errors'):
                    error_count += 1
                    self.logger.warning(f"⚠️  记录 {record_id} 下载有错误")
                elif result.get('downloaded_files'):
                    success_count += 1
                    self.logger.info(f"✅ 记录 {record_id} 处理完成，下载 {len(result['downloaded_files'])} 个文件")
                else:
                    no_files_count += 1
                    self.logger.info(f"ℹ️  记录 {record_id} 无文件可下载")
            
            # 保存结果到JSON文件
            summary = {
                'timestamp': timestamp,
                'total_goods_records': len(goods_records),
                'success_count': success_count,
                'error_count': error_count,
                'no_files_count': no_files_count,
                'processed_records': len(results),
                'goods_record_ids': goods_record_ids,
                'results': results
            }
            
            with open(results_file, 'w', encoding='utf-8') as f:
                json.dump(summary, f, ensure_ascii=False, indent=2)
                
            self.logger.info(f"💾 结果已保存: {results_file}")
            
            # 打印摘要
            self.logger.info("=" * 60)
            self.logger.info("📊 处理摘要:")
            self.logger.info(f"   goods类别记录总数: {len(goods_records)}")
            self.logger.info(f"   goods类别record_id: {', '.join(goods_record_ids)}")
            self.logger.info(f"   成功处理: {success_count}")
            self.logger.info(f"   处理失败: {error_count}")
            self.logger.info(f"   无文件记录: {no_files_count}")
            self.logger.info("=" * 60)
            
            return summary
            
        except Exception as e:
            self.logger.error(f"❌ 处理JSON文件失败: {e}")
            return {'success': False, 'error': str(e)}
        finally:
            if self.conn:
                self.disconnect_db()

def main():
    """主函数 - 使用示例"""
    # 创建下载器实例（使用默认配置）
    downloader = GoodsFileDownloader()
    
    # 获取JSON文件路径
    json_file_path = input(f"请输入JSON文件路径（直接回车使用默认路径 {FILE_CONFIG.get('default_json_path')}）: ").strip()
    
    if not json_file_path:
        json_file_path = FILE_CONFIG.get('default_json_path')
    
    # 验证文件是否存在
    if not os.path.exists(json_file_path):
        print(f"❌ 文件不存在: {json_file_path}")
        return
    
    # 处理文件下载
    result = downloader.process_json_file(json_file_path)
    
    if result.get('success', True):
        print("✅ 文件下载任务完成")
    else:
        print(f"❌ 文件下载任务失败: {result.get('error')}")

if __name__ == "__main__":
    main()
