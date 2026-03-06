# D:\code\project\scripts\20251227\20251227_version_1\generate_vector_cache.py
"""
生成向量缓存文件
将三个类别(goods, service, project)的示例文本向量化并保存
"""

import json
import numpy as np
from pathlib import Path
import sys
from datetime import datetime

# 添加当前路径
current_dir = Path(__file__).parent

def load_model():
    """加载text2vec模型"""
    try:
        from sentence_transformers import SentenceTransformer, models
        
        model_path = r"D:\code\model\text2vec-large-chinese"
        print(f"✅ 加载模型: {model_path}")
        
        # 检查模型路径是否存在
        model_dir = Path(model_path)
        if not model_dir.exists():
            print(f"❌ 模型路径不存在: {model_path}")
            print("请确保模型已下载到正确位置")
            return None
        
        # 手动构建模型
        word_embedding_model = models.Transformer(model_path)
        pooling_model = models.Pooling(word_embedding_model.get_word_embedding_dimension())
        model = SentenceTransformer(modules=[word_embedding_model, pooling_model])
        
        # 测试模型
        test_text = "这是一个测试"
        embedding = model.encode([test_text])
        print(f"✅ 模型测试通过，输出维度: {embedding.shape[1]}")
        
        return model
    except Exception as e:
        print(f"❌ 加载模型失败: {e}")
        return None

def generate_cache_files():
    """生成向量缓存文件"""
    
    print("=" * 50)
    print("📊 开始生成向量缓存...")
    print("=" * 50)
    
    # 1. 加载模型
    model = load_model()
    if model is None:
        print("❌ 无法加载文本嵌入模型")
        return False
    
    # 2. 定义三个类别的典型示例文本
    category_examples = {
    "goods": [
        # 核心特征：明确列出具体物品、设备、耗材、用品，或动词为“采购”“购买”“购置”+物品
        "采购一批台式电脑",
        "购买办公桌椅和打印机",
        "教学用实验仪器购置",
        "医疗耗材一批（口罩、手套、试剂）",
        "竞价采购硒鼓墨盒",
        "采购服务器、交换机等网络设备",
        "购买矿泉水、纸巾等日常用品",
        "家具一批（沙发、文件柜）",
        "采购无人机、云台相机等摄影器材",
        "化粪池采购",
        "采购两辆商务车",
        "电子发票系统软件许可（非服务）",
        # 新增：覆盖“采购项目”类表述
        "校园监控设备采购项目",
        "信息化系统硬件采购项目",
        "医疗设备购置项目（含CT机、监护仪）"
    ],
    "service": [
        # 核心特征：动词为“服务”“维护”“咨询”“培训”“测评”“监理”“审计”，且无实物交付
        "信息系统等级保护测评服务",
        "电子胃镜维修保养服务",
        "技术培训与操作指导服务",
        "档案整理及数字化加工服务",
        "水闸渠道清淤服务",
        "设计咨询与方案编制服务",
        "工程监理服务",
        "财务审计与评估服务",
        "广告投放运营服务",
        "公车保险服务"
    ],
    "project": [
        # 核心特征：涉及“建设”“施工”“改造”“整治”“开发”“安装（系统性）”“工程”“基础设施”
        "教学楼地面维修改造工程",
        "农村公路安全生命防护工程建设",
        "智慧校园监控系统建设项目",
        "老旧小区自来水管网迁改工程",
        "废弃矿山生态修复示范工程",
        "水库除险加固工程",
        "数字检察办案中心建设",
        "土地开发整理项目",
        "桥梁新建及道路加宽工程",
        "污水处理厂污泥处置转运工程（整体实施）"
    ]
}
    
    # 3. 为每个类别计算向量
    print("\n🤖 处理每个类别的示例文本...")
    category_vectors = {}
    categories = ["goods", "service", "project"]
    
    for category in categories:
        examples = category_examples[category]
        print(f"  📋 处理 {category}: {len(examples)} 个示例")
        
        try:
            # 对示例进行编码
            embeddings = model.encode(examples, normalize_embeddings=True)
            
            # 计算平均向量
            avg_vector = np.mean(embeddings, axis=0)
            category_vectors[category] = avg_vector
            
            print(f"    ✅ 完成，向量维度: {avg_vector.shape}")
        except Exception as e:
            print(f"    ❌ 处理 {category} 失败: {e}")
            return False
    
    # 4. 创建缓存目录
    cache_dir = current_dir / "vector_cache"
    cache_dir.mkdir(exist_ok=True)
    
    # 5. 保存类别文件
    types_file = cache_dir / "procurement_types.json"
    with open(types_file, "w", encoding="utf-8") as f:
        json.dump(categories, f, ensure_ascii=False, indent=2)
    print(f"\n💾 保存类别文件: {types_file}")
    
    # 6. 保存向量文件
    vectors_array = np.array([category_vectors[cat] for cat in categories])
    vectors_file = cache_dir / "procurement_type_vectors.npy"
    np.save(vectors_file, vectors_array)
    print(f"💾 保存向量文件: {vectors_file}")
    print(f"   向量维度: {vectors_array.shape}")
    
    # 7. 计算并显示类别间相似度
    try:
        from sklearn.metrics.pairwise import cosine_similarity
        
        sim_matrix = cosine_similarity(vectors_array)
        print(f"\n📈 类别间余弦相似度矩阵:")
        print("      goods   service   project")
        for i, cat1 in enumerate(categories):
            row = f"{cat1:7}"
            for j, cat2 in enumerate(categories):
                row += f" {sim_matrix[i][j]:8.4f}"
            print(row)
        
        # 分析建议
        print(f"\n💡 分析建议:")
        if sim_matrix[0][1] > 0.7:  # goods和service相似度太高
            print(f"  ⚠️  goods和service相似度较高({sim_matrix[0][1]:.4f})，可能需要调整示例文本")
        if sim_matrix[0][2] > 0.7:  # goods和project相似度太高
            print(f"  ⚠️  goods和project相似度较高({sim_matrix[0][2]:.4f})，可能需要调整示例文本")
        if sim_matrix[1][2] > 0.7:  # service和project相似度太高
            print(f"  ⚠️  service和project相似度较高({sim_matrix[1][2]:.4f})，可能需要调整示例文本")
            
    except Exception as e:
        print(f"⚠️  无法计算相似度矩阵: {e}")
    
    # 8. 保存详细信息
    info = {
        "generated_at": datetime.now().isoformat(),
        "categories": categories,
        "embedding_dimension": vectors_array.shape[1],
        "example_count_per_category": {k: len(category_examples[k]) for k in categories},
        "vector_shape": vectors_array.shape
    }
    
    info_file = cache_dir / "vector_cache_info.json"
    with open(info_file, "w", encoding="utf-8") as f:
        json.dump(info, f, ensure_ascii=False, indent=2)
    print(f"\n💾 保存信息文件: {info_file}")
    
    print("\n" + "=" * 50)
    print("✅ 向量缓存生成完成!")
    print(f"💡 向量已保存到: {cache_dir}")
    print("=" * 50)
    
    return True

def test_cache_files():
    """测试生成的缓存文件"""
    cache_dir = current_dir / "vector_cache"
    
    print("\n🧪 测试生成的缓存文件...")
    
    if not cache_dir.exists():
        print("❌ 缓存目录不存在")
        return False
    
    try:
        # 测试类别文件
        types_file = cache_dir / "procurement_types.json"
        if not types_file.exists():
            print(f"❌ 类别文件不存在: {types_file}")
            return False
        
        with open(types_file, "r", encoding="utf-8") as f:
            categories = json.load(f)
        print(f"✅ 加载类别: {categories}")
        
        # 测试向量文件
        vectors_file = cache_dir / "procurement_type_vectors.npy"
        if not vectors_file.exists():
            print(f"❌ 向量文件不存在: {vectors_file}")
            return False
        
        vectors = np.load(vectors_file)
        print(f"✅ 加载向量: {vectors.shape}")
        
        # 测试信息文件
        info_file = cache_dir / "vector_cache_info.json"
        if info_file.exists():
            with open(info_file, "r", encoding="utf-8") as f:
                info = json.load(f)
            print(f"✅ 加载信息: 生成时间={info.get('generated_at')}")
        
        # 测试简单的相似度计算
        if len(categories) > 0:
            test_vector = vectors[0]  # 第一个类别的向量
            print(f"✅ 向量示例: 前5个值={test_vector[:5]}")
        
        return True
        
    except Exception as e:
        print(f"❌ 测试缓存文件失败: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    print("🚀 向量缓存生成工具")
    print("📁 工作目录:", current_dir)
    print("📁 模型路径: D:\\code\\model\\text2vec-large-chinese")
    print()
    
    success = False
    try:
        success = generate_cache_files()
    except Exception as e:
        print(f"❌ 生成过程中出现异常: {e}")
        import traceback
        traceback.print_exc()
    
    if success:
        test_cache_files()
