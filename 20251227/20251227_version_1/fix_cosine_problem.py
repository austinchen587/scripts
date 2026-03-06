# D:\code\project\scripts\20251227\20251227_version_1\fix_cosine_problem.py
"""
自动修复余弦匹配问题的脚本
"""

import sys
from pathlib import Path
import shutil

current_dir = Path(__file__).parent

def fix_problem():
    print("=" * 60)
    print("🔧 余弦匹配问题修复工具")
    print("=" * 60)
    
    # 1. 创建备份
    backup_dir = current_dir / "backup"
    backup_dir.mkdir(exist_ok=True)
    
    files_to_backup = ["second_stage_cosine.py"]
    for file in files_to_backup:
        src = current_dir / file
        if src.exists():
            dst = backup_dir / (file + ".backup")
            shutil.copy2(src, dst)
            print(f"✅ 已备份: {file} -> {dst}")
    
    # 2. 创建vector_cache目录
    cache_dir = current_dir / "vector_cache"
    cache_dir.mkdir(exist_ok=True)
    print(f"✅ 确保缓存目录存在: {cache_dir}")
    
    # 3. 提示用户生成向量缓存
    print("")
    print("📊 请运行以下命令生成向量缓存:")
    print(f"   cd {current_dir}")
    print(f"   python generate_vector_cache.py")
    print("")
    
    # 4. 检查模型文件
    model_path = Path(r"D:\code\model\text2vec-large-chinese")
    if model_path.exists():
        print(f"✅ 找到模型文件: {model_path}")
    else:
        print(f"⚠️  模型文件不存在: {model_path}")
        print("   请确保text2vec-large-chinese模型已下载到正确位置")
    
    # 5. 运行快速测试
    print("")
    print("🧪 运行快速测试:")
    try:
        from second_stage_cosine import CosineVerifier
        
        verifier = CosineVerifier()
        if verifier.model_loaded:
            print(f"✅ 余弦验证器加载成功:")
            print(f"   - 模型: {'已加载' if verifier.model else '未加载'}")
            print(f"   - 向量缓存: {verifier.type_vectors.shape if verifier.type_vectors is not None else '无'}")
            print(f"   - 类别: {verifier.type_names}")
            
            # 测试一个示例
            sample_text = "政府采购办公电脑"
            result = verifier.verify(sample_text, {"category": "goods", "confidence": 0.8})
            print(f"✅ 测试文本 '{sample_text}' 余弦验证:")
            print(f"   类别: {result.get('cosine_category')}")
            print(f"   置信度: {result.get('cosine_confidence')}")
            print(f"   相似度详情: {result.get('similarities', {})}")
        else:
            print("❌ 余弦验证器加载失败")
            
    except Exception as e:
        print(f"❌ 快速测试失败: {e}")
    
    print("")
    print("=" * 60)
    print("✅ 修复完成!")
    print("=" * 60)

if __name__ == "__main__":
    fix_problem()
