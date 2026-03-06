from sentence_transformers import SentenceTransformer, models
from config import TEXT2VEC_MODEL_PATH

class Text2VecLargeChinese:
    def __init__(self):
        print("🔍 加载 text2vec-large-chinese 模型...")
        word_embedding_model = models.Transformer(TEXT2VEC_MODEL_PATH)
        pooling_model = models.Pooling(word_embedding_model.get_word_embedding_dimension())
        self.model = SentenceTransformer(modules=[word_embedding_model, pooling_model], device='cuda')
        print("✅ 模型加载完成")

    def encode(self, texts: list[str]) -> list[list[float]]:
        return self.model.encode(texts, normalize_embeddings=True).tolist()
