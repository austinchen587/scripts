# D:\code\project\scripts\20251227\20260109_step_1\second_stage_cosine.py
"""
第二阶段：余弦相似度验证器 (最终优化版)
1. 实现了 Top-K 多示例匹配，解决单中心语义模糊问题。
2. 针对性优化了向量库：
   - Goods: 补充了办公耗材、慰问品、保险柜等盲区。
   - Service: 补充了病虫害防治、劳务派遣等。
   - Project: 剔除了"系统建设"等软词，注入了"土石方/硬化/改造"等硬核土建词。
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
    print("  注意：sentence-transformers 或 scikit-learn 未安装，余弦验证将不可用")

class CosineVerifier:
    """余弦相似度验证器"""
    
    def __init__(self):
        self.model = None
        self.type_vectors = None 
        self.type_labels = None  
        self.model_loaded = False
        
        if EMBEDDING_AVAILABLE:
            self._load_model()
    
    def _load_model(self):
        """加载模型和向量缓存"""
        try:
            print(" 开始加载余弦验证器...")
            
            # 1. 加载模型
            try:
                # 请确保此路径指向您本地的模型文件夹
                model_path = r"D:\code\model\text2vec-large-chinese" 
                word_emb = models.Transformer(model_path)
                pooling = models.Pooling(word_emb.get_word_embedding_dimension())
                self.model = SentenceTransformer(modules=[word_emb, pooling])
                print(f" 模型加载成功")
            except Exception as model_error:
                print(f" 模型加载失败: {model_error}")
                return
            
            # 2. 加载或生成向量缓存
            cache_dir = current_dir / "vector_cache"
            cache_dir.mkdir(exist_ok=True)
            
            # 🟢 使用 v3 版本后缀，强制区分旧缓存，确保新词条生效
            vectors_file = cache_dir / "procurement_vectors_full_v3.npy"
            labels_file = cache_dir / "procurement_labels_v3.json"
            
            if not vectors_file.exists() or not labels_file.exists():
                print(" 向量缓存不存在或版本过旧，开始生成...")
                self._generate_vector_cache(vectors_file, labels_file)
            else:
                try:
                    self.type_vectors = np.load(vectors_file)
                    with open(labels_file, "r", encoding="utf-8") as f:
                        self.type_labels = json.load(f)
                    
                    # 简单维度检查
                    if self.type_vectors.shape[0] != len(self.type_labels):
                        print(" ⚠️ 向量与标签数量不匹配，重新生成...")
                        self._generate_vector_cache(vectors_file, labels_file)
                    else:
                        print(f" 加载向量缓存成功: {self.type_vectors.shape}")
                        
                except Exception as cache_error:
                    print(f" 加载缓存失败: {cache_error}")
                    self._generate_vector_cache(vectors_file, labels_file)
            
            self.model_loaded = True
            
        except Exception as e:
            print(f" 加载余弦验证器失败: {e}")
            self.model_loaded = False
    
    def _generate_vector_cache(self, vectors_file, labels_file):
        """生成向量缓存文件 (Top-K 多示例模式)"""
        print("🔨 生成全量向量缓存 (Project纯化版)...")
        
        try:
            category_examples = {
                "goods": [
                    "采购一批台式电脑", "购买办公桌椅和打印机", "教学用实验仪器购置", 
                    "医疗耗材一批", "竞价采购硒鼓墨盒", "采购服务器交换机", 
                    "购买矿泉水纸巾", "家具一批", "采购无人机", "化粪池采购", 
                    "采购商务车", "软件许可授权", "校园监控设备采购", 
                    "信息化硬件采购", "医疗设备购置",
                    # ⬇️ 补强 Goods (针对之前的Badcase)
                    "复印纸办公用纸采购", "春节慰问品物资", 
                    "档案盒文件袋采购", "保险柜防盗门采购"
                ],
                "service": [
                    "信息系统等级保护测评", "设备维修保养服务", "技术培训操作指导", 
                    "档案整理数字化加工", "渠道清淤服务", "设计咨询方案编制", 
                    "工程监理服务", "财务审计评估", "广告投放运营", "保险服务",
                    "物业管理服务", "系统运维服务", "劳务外包服务",
                    # ⬇️ 补强 Service (针对之前的Badcase)
                    "病虫害防控消杀服务", "劳务派遣人员服务"
                ],
                "project": [
                    # 🟢 纯化后的工程列表 (Hardcore Civil Engineering)
                    # 剔除了"系统建设"等容易混淆的软词
                    # 1. 基础修缮
                    "教学楼维修改造工程", "老旧小区改造项目", "外立面整治改造",
                    # 2. 市政土建
                    "公路路面硬化工程", "土石方填筑施工", "管网迁改工程", 
                    "道路拓宽改造", "桥梁新建工程", "生态修复示范工程",
                    # 3. 结构与安装
                    "水库除险加固", "防水防腐保温工程", "钢结构主体施工",
                    "室外配套设施建设", "拆除工程", "土地开发整理项目"
                ]
            }
            
            all_vectors = []
            all_labels = []
            
            for category, examples in category_examples.items():
                print(f"  处理类别: {category}, 示例数: {len(examples)}")
                embeddings = self.model.encode(examples, normalize_embeddings=True)
                all_vectors.append(embeddings)
                all_labels.extend([category] * len(examples))
            
            full_matrix = np.vstack(all_vectors)
            
            np.save(vectors_file, full_matrix)
            with open(labels_file, "w", encoding="utf-8") as f:
                json.dump(all_labels, f, ensure_ascii=False)
            
            self.type_vectors = full_matrix
            self.type_labels = all_labels
            print(f" 向量缓存生成完成!")
            
        except Exception as e:
            print(f" 生成向量缓存失败: {e}")
            # 后备 Dummy 数据
            self.type_vectors = np.random.randn(3, 1024).astype(np.float32)
            self.type_labels = ["goods", "service", "project"]
    
    def verify(self, text, keyword_result):
        """Top-K 语义匹配逻辑"""
        if not text or not self.model_loaded:
            return {
                "cosine_category": keyword_result.get("category", "goods"),
                "cosine_confidence": 0.0,
                "verified": False
            }
        
        try:
            text_emb = self.model.encode([text], normalize_embeddings=True)
            similarities = cosine_similarity(text_emb, self.type_vectors)[0]
            
            category_scores = {}
            top_k = 3
            
            for cat in ["goods", "service", "project"]:
                indices = [i for i, label in enumerate(self.type_labels) if label == cat]
                if not indices:
                    category_scores[cat] = 0.0
                    continue
                
                cat_sims = similarities[indices]
                k_actual = min(top_k, len(cat_sims))
                # 取该类别下最相似的 Top-K 个样本的平均分
                best_k_sims = np.sort(cat_sims)[-k_actual:]
                category_scores[cat] = float(np.mean(best_k_sims))
            
            best_category = max(category_scores, key=category_scores.get)
            best_similarity = category_scores[best_category]
            sim_dict = {k: round(v, 4) for k, v in category_scores.items()}
            
            return {
                "cosine_category": best_category,
                "cosine_confidence": round(best_similarity, 4), # 保持真实分数
                "best_similarity": round(best_similarity, 4),
                "similarities": sim_dict,
                "verified": True,
                "consistent": (keyword_result.get("category") == best_category)
            }
            
        except Exception as e:
            return {"cosine_category": keyword_result.get("category", "goods"), "cosine_confidence": 0.0, "verified": False}