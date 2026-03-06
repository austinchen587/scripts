# rag_retriever.py
from vectorizer import TextVectorizer
from vector_store import HistoricalCaseRetriever
from config import TOP_K_CASES

_vectorizer = None
_retriever = None



def get_similar_cases(requirement_text: str, min_similarity_threshold=0.6):
    """
    动态获取相似案例，根据相似度决定是否参考
    """
    global _vectorizer, _retriever
    if _vectorizer is None:
        _vectorizer = TextVectorizer()
    if _retriever is None:
        _retriever = HistoricalCaseRetriever()
    
    # 编码查询文本
    emb = _vectorizer.encode(requirement_text)
    
    # 检索最多TOP_K个案例
    raw_cases = _retriever.retrieve(emb, top_k=TOP_K_CASES)
    
    # 根据相似度阈值过滤
    filtered_cases = []
    for case in raw_cases:
        # 将距离转换为相似度（假设距离越小越相似）
        distance = case.get('distance', 10)  # 默认大距离
        similarity = 1.0 / (1.0 + distance)  # 简单转换
        
        if similarity >= min_similarity_threshold:
            case['similarity'] = round(similarity, 3)
            filtered_cases.append(case)
    
    # 按相似度排序
    filtered_cases.sort(key=lambda x: x.get('similarity', 0), reverse=True)
    
    print(f"[RAG] 相似度分析: 检索到 {len(raw_cases)} 个，过滤后 {len(filtered_cases)} 个（阈值: {min_similarity_threshold})")
    
    return filtered_cases

    '''

def get_similar_cases(requirement_text: str, min_similarity_threshold=0.6):
    """
    禁用RAG功能，直接返回空列表
    """
    print(f"[RAG] ❌ RAG功能已禁用，直接返回空列表")
    return []  # 总是返回空列表，跳过所有向量化查询
'''