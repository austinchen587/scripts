# D:\code\project\scripts\20251227\20251227_version_1\second_stage_cosine.py
"""
第二阶段：余弦相似度验证器
使用语义向量进行二次验证
"""

import json
import numpy as np
from pathlib import Path
import sys

# 添加当前路径
current_dir = Path(__file__).parent

try:
    from sentence_transformers import SentenceTransformer, models
    from sklearn.metrics.pairwise import cosine_similarity
    EMBEDDING_AVAILABLE = True
except ImportError:
    EMBEDDING_AVAILABLE = False
    print("⚠️  注意：sentence-transformers 或 scikit-learn 未安装，余弦验证将不可用")

class CosineVerifier:
    """余弦相似度验证器"""
    
    def __init__(self):
        self.model = None
        self.type_vectors = None
        self.type_names = None
        self.model_loaded = False
        
        if EMBEDDING_AVAILABLE:
            self._load_model()
    
    def _load_model(self):
        """加载模型和向量缓存"""
        try:
            print("🚀 开始加载余弦验证器...")
            
            # 1. 首先尝试加载模型
            try:
                model_path = r"D:\code\model\text2vec-large-chinese"
                print(f"📥 加载模型: {model_path}")
                
                # 与download_model.py相同的方式
                word_emb = models.Transformer(model_path)
                pooling = models.Pooling(word_emb.get_word_embedding_dimension())
                self.model = SentenceTransformer(modules=[word_emb, pooling])
                
                print(f"✅ 模型加载成功")
            except Exception as model_error:
                print(f"❌ 模型加载失败: {model_error}")
                return
            
            # 2. 加载或生成向量缓存
            cache_dir = current_dir / "vector_cache"
            cache_dir.mkdir(exist_ok=True)
            
            types_file = cache_dir / "procurement_types.json"
            vectors_file = cache_dir / "procurement_type_vectors.npy"
            
            # 如果缓存不存在，生成它
            if not types_file.exists() or not vectors_file.exists():
                print("📊 向量缓存不存在，开始生成...")
                self._generate_vector_cache()
            else:
                # 加载现有缓存
                try:
                    with open(types_file, "r", encoding="utf-8") as f:
                        self.type_names = json.load(f)
                    print(f"✅ 加载类别: {self.type_names}")
                    
                    self.type_vectors = np.load(vectors_file)
                    print(f"✅ 加载向量缓存: {self.type_vectors.shape}")
                    
                    # 测试维度一致性
                    test_text = "测试文本"
                    test_embedding = self.model.encode([test_text])
                    
                    if test_embedding.shape[1] != self.type_vectors.shape[1]:
                        print(f"⚠️  维度不匹配: 模型={test_embedding.shape[1]}, 缓存={self.type_vectors.shape[1]}")
                        print("🔁 重新生成向量缓存...")
                        self._generate_vector_cache()
                    
                except Exception as cache_error:
                    print(f"❌ 加载缓存失败: {cache_error}")
                    print("🔁 重新生成向量缓存...")
                    self._generate_vector_cache()
            
            self.model_loaded = True
            print("✅ 余弦验证器加载完成!")
            
        except Exception as e:
            print(f"❌ 加载余弦验证器失败: {e}")
            self.model_loaded = False
    
    def _generate_vector_cache(self):
        """生成向量缓存文件"""
        print("🔨 生成向量缓存...")
        
        try:
            # 类别示例文本
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
            
            cache_dir = current_dir / "vector_cache"
            cache_dir.mkdir(exist_ok=True)
            
            # 为每个类别计算平均向量
            category_vectors = []
            categories = ["goods", "service", "project"]
            
            for category in categories:
                examples = category_examples[category]
                print(f"  处理类别: {category}, 示例数: {len(examples)}")
                embeddings = self.model.encode(examples, normalize_embeddings=True)
                avg_vector = np.mean(embeddings, axis=0)
                category_vectors.append(avg_vector)
            
            # 保存类别
            types_file = cache_dir / "procurement_types.json"
            with open(types_file, "w", encoding="utf-8") as f:
                json.dump(categories, f, ensure_ascii=False, indent=2)
            
            # 保存向量
            vectors_array = np.array(category_vectors)
            vectors_file = cache_dir / "procurement_type_vectors.npy"
            np.save(vectors_file, vectors_array)
            
            # 更新实例变量
            self.type_names = categories
            self.type_vectors = vectors_array
            
            print(f"✅ 向量缓存生成完成: {vectors_array.shape}")
            
        except Exception as e:
            print(f"❌ 生成向量缓存失败: {e}")
            # 创建默认向量作为后备
            self.type_names = ["goods", "service", "project"]
            self.type_vectors = np.random.randn(3, 1024).astype(np.float32)  # text2vec通常输出1024维
    
    def verify(self, text, keyword_result):
        """
        基于余弦相似度的验证
        
        Args:
            text: 项目名称文本
            keyword_result: 第一阶段关键词分类结果
        
        Returns:
            dict: 验证结果
        """
        if not text or not isinstance(text, str) or not text.strip():
            return {
                "cosine_category": keyword_result.get("category", "goods"),
                "cosine_confidence": 0.0,
                "similarities": {},
                "verified": False,
                "error": "文本为空"
            }
        
        if not self.model_loaded:
            return {
                "cosine_category": keyword_result.get("category", "goods"),
                "cosine_confidence": 0.0,
                "similarities": {},
                "verified": False,
                "error": "模型未加载"
            }
        
        try:
            # 生成文本向量
            text_emb = self.model.encode([text], normalize_embeddings=True)
            
            # 检查维度一致性
            if text_emb.shape[1] != self.type_vectors.shape[1]:
                print(f"🚨 维度不匹配! 文本: {text_emb.shape[1]}, 缓存: {self.type_vectors.shape[1]}")
                # 重新生成缓存
                self._generate_vector_cache()
            
            # 计算余弦相似度
            similarities = cosine_similarity(text_emb, self.type_vectors)[0]
            
            # 找到最相似的类别
            best_idx = int(np.argmax(similarities))
            best_category = self.type_names[best_idx]
            best_similarity = float(similarities[best_idx])
            
            # 整理相似度字典
            sim_dict = {self.type_names[i]: float(similarities[i]) for i in range(len(self.type_names))}
            
            # 计算置信度
            confidence = best_similarity
            
            # 增加基于相似度差异的修正
            sorted_sims = sorted(similarities, reverse=True)
            if len(sorted_sims) > 1:
                gap = sorted_sims[0] - sorted_sims[1]
                if gap > 0.15:  # 如果差距很大，增加置信度
                    confidence = min(best_similarity * 1.1, 0.95)
                elif gap < 0.05:  # 如果差距很小，降低置信度
                    confidence = best_similarity * 0.8
            
            # 确保置信度在合理范围
            confidence = min(max(confidence, 0.3), 0.95)
            confidence = round(confidence, 4)
            best_similarity = round(best_similarity, 4)
            keyword_category = keyword_result.get("category")
            is_consistent = (keyword_category == best_category)
            
            return {
                "cosine_category": best_category,
                "cosine_confidence": confidence,
                "best_similarity": best_similarity,
                "similarities": sim_dict,
                "verified": True,
                "consistent": is_consistent
            }
            
        except Exception as e:
            error_msg = str(e)
            return {
                "cosine_category": keyword_result.get("category", "goods"),
                "cosine_confidence": 0.0,
                "similarities": {},
                "verified": False,
                "error": error_msg
            }
