# vector_store.py
import chromadb
from config import VECTOR_DB_PATH



class HistoricalCaseRetriever:
    def __init__(self):
        self.client = chromadb.PersistentClient(path=VECTOR_DB_PATH)
        self.collection = self.client.get_collection("procurement_requirements")

    def retrieve(self, query_embedding, top_k=3, min_similarity=0.4):
        results = self.collection.query(
            query_embeddings=[query_embedding],
            n_results=top_k,
            include=["documents", "metadatas", "distances"]  # ← 必须包含 distances
        )
        
        cases = []
        if results["ids"] and len(results["ids"][0]) > 0:
            for i in range(len(results["ids"][0])):
                distance = results["distances"][0][i]
                # Chroma 使用 L2 距离，越小越相似。转换为相似度（可选）
                # 或直接设距离阈值（例如 distance < 1.5）
                if distance < 1.8:  # ← 根据你的模型调整！text2vec-large-chinese 的典型阈值
                    case = {
                        "case_id": results["ids"][0][i],
                        "content": results["documents"][0][i],
                        "metadata": results["metadatas"][0][i],
                        "distance": distance
                    }
                    cases.append(case)
        return cases
'''


class HistoricalCaseRetriever:
    def __init__(self):
        # 仍然初始化，但什么都不做
        self.client = None
        self.collection = None
        print("[RAG] ❌ RAG功能已禁用")
    def retrieve(self, query_embedding, top_k=3, min_similarity=0.4):
        """直接返回空列表，不执行任何检索"""
        print(f"[RAG] ❌ 检索功能已禁用，返回空列表")
        return []  # 总是返回空列表


        '''