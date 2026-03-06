# D:\code\project\scripts\20251227\20251227_version_1\config.py
"""
分类阈值配置
"""

# ========== 第一阶段：关键词分类阈值 ==========
KEYWORD_THRESHOLDS = {
    "high_confidence": 0.80,      # 原值：>=0.85，太高了，直接结束
    "medium_confidence": 0.65,    # 原值：>=0.70（应该进入第二阶段）
    "low_confidence": 0.50        # 原值：>=0.60（应该进入第二阶段）
}

# ========== 第二阶段：余弦相似度验证阈值 ==========
COSINE_THRESHOLDS = {
    "high_confidence": 0.75,      # 高置信度阈值
    "acceptable": 0.60,           # 可接受阈值
    "requires_verification": 0.45 # 需要复核阈值
}

# ========== 第三阶段：集成决策权重 ==========
ENSEMBLE_WEIGHTS = {
    "keyword_weight": 0.4,        # 关键词权重
    "cosine_weight": 0.6,         # 余弦相似度权重（更重要）
    "tie_breaker_bias": 0.55      # 平局时偏向语义
}

# ========== 分类类别 ==========
PROCUREMENT_CATEGORIES = ["goods", "service", "project"]

# ========== 数据库配置 ==========
DB_CONFIG = {
    "host": "localhost",
    "port": 5432,
    "database": "your_database",  # 请修改为您的真实信息
    "user": "your_user",
    "password": "your_password"
}
