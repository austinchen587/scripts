# main.py
import os
import json
from pathlib import Path
from utils import setup_logging, load_json_file, save_results
from keyword_generator import KeywordGenerator

def main():
    # 设置日志
    setup_logging()
    
    print("=== 电商商品搜索关键词生成系统 ===")
    print("支持平台: 1688、淘宝、京东、拼多多")
    print()
    
    # 获取用户输入的JSON文件路径
    json_file_path = input("请输入JSON文件路径: ").strip()
    
    if not os.path.exists(json_file_path):
        print(f"错误: 文件不存在 - {json_file_path}")
        return
    
    # 加载JSON数据
    data = load_json_file(json_file_path)
    if not data or 'results' not in data:
        print("错误: 无效的JSON格式或缺少results字段")
        return
    
    # 初始化生成器
    generator = KeywordGenerator()
    results = []
    
    print(f"\n开始处理 {len(data['results'])} 条记录...")
    
    # 处理每条记录
    for i, record in enumerate(data['results'], 1):
        print(f"\n[{i}/{len(data['results'])}] 处理记录 ID: {record['record_id']}")
        
        result = generator.process_record(record)
        results.append(result)
        
        # 显示进度
        if result['status'] == 'success':
            keywords = result.get('search_keywords', [])
            print(f"   ✓ 成功生成 {len(keywords)} 个关键词")
            for kw in keywords:
                print(f"     - {kw['commodity_name']}:")
                for platform_kw in kw['platform_keywords']:
                    print(f"       - {platform_kw['platform']}: {', '.join(platform_kw['keywords'])}")
        else:
            print(f"   ✗ 处理失败: {result.get('error', '未知错误')}")
        
        # 每次处理完一条记录后立即写入JSON文件
        output_path = Path(json_file_path).parent / "search_keywords_results.json"
        if save_results(results, output_path):
            print(f"   ✓ 结果已保存到: {output_path}")
        else:
            print(f"   ✗ 结果保存失败")
    
    # 统计信息
    success_count = sum(1 for r in results if r['status'] == 'success')
    total_keywords = sum(len(r.get('search_keywords', [])) for r in results)
    
    print(f"\n统计信息:")
    print(f"- 成功处理: {success_count}/{len(results)} 条记录")
    print(f"- 总生成关键词: {total_keywords} 个")
    print(f"- 成功率: {success_count/len(results)*100:.1f}%")

if __name__ == "__main__":
    main()
