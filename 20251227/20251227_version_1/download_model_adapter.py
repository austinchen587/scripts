"""
适配器：用于调用外部的download_model.py
"""

import sys
from pathlib import Path

def load_text2vec_model():
    """尝试从不同位置加载text2vec模型"""
    possible_paths = [
        Path("D:/code/model/download_model.py"),
        Path(__file__).parent.parent.parent / "model" / "download_model.py",
        Path("D:/code/project/scripts/model/download_model.py"),
    ]
    
    for model_path in possible_paths:
        if model_path.exists():
            try:
                # 动态导入
                import importlib.util
                spec = importlib.util.spec_from_file_location("download_model", str(model_path))
                download_module = importlib.util.module_from_spec(spec)
                
                # 需要将模型目录添加到路径
                model_dir = str(model_path.parent)
                if model_dir not in sys.path:
                    sys.path.append(model_dir)
                
                spec.loader.exec_module(download_module)
                
                # 调用函数
                return download_module.load_text2vec_model()
            except Exception as e:
                print(f"⚠️  加载 {model_path} 失败: {e}")
                continue
    
    # 如果都失败，尝试直接加载
    try:
        model_path = r"D:\code\model\text2vec-large-chinese"
        from sentence_transformers import SentenceTransformer, models
        
        word_emb = models.Transformer(model_path)
        pooling = models.Pooling(word_emb.get_word_embedding_dimension())
        model = SentenceTransformer(modules=[word_emb, pooling])
        
        return model
    except Exception as e:
        print(f"❌ 所有加载方法都失败: {e}")
        return None
