import chromadb
from pathlib import Path
from config import VECTOR_DB_DIR

class ProcurementVectorStore:
    def __init__(self):
        self.client = chromadb.PersistentClient(path=str(VECTOR_DB_DIR))
        # 显式禁用 embedding function
        self.collection = self.client.get_or_create_collection(
            name="procurement_requirements",
            metadata={"hnsw:space": "cosine"},
            embedding_function=None
        )

    def add_documents(self, documents: list[str], metadatas: list[dict], ids: list[str], embeddings: list[list[float]]):
        # 必须传入 embeddings
        self.collection.add(
            documents=documents,
            metadatas=metadatas,
            ids=ids,
            embeddings=embeddings
        )
        print(f"✅ 已存入 {len(documents)} 条向量记录")

    def query(self, query_embeddings: list[list[float]], n_results: int = 5):
        return self.collection.query(
            query_embeddings=query_embeddings,
            n_results=n_results
        )
