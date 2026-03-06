# D:\code\project\scripts\know_099\graph_engine.py
import json
import re
from config import TABLE_NODES, TABLE_EDGES

class DataCleaner:
    """
    数据清洗与校验器 (V3.0 平台差异化版 - 基于数据库字段)
    """
    
    # 1. 基础黑名单 (所有平台通用)
    BASIC_INVALID = {
        "无", "未知", "品牌", "正品", "新款", "潮牌", "外贸", "清仓", 
        "热销", "推荐", "同款", "/", "", "nan", "null", "none",
        "男装", "女装", "童装", "冬季", "夏季", "秋季", "春季", "官方", "旗舰店"
    }

    # 2. 营销黑名单 (针对淘宝/1688，防止污染骨架)
    MARKETING_INVALID = {
        "厂家直销", "一件代发", "现货", "批发", "定制", "包邮", "特价",
        "ins", "ins风", "韩版", "港风", "日系", "网红", "爆款", "平替",
        "源头工厂", "专供", "手工", "DIY", "加厚", "保暖", "显瘦", "同款"
    }

    @staticmethod
    def clean_brand(text, platform_raw):
        """
        根据平台进行差异化品牌清洗
        """
        if not text: return None
        clean_text = str(text).strip()
        
        # --- 基础清洗 ---
        if len(clean_text) < 2: return None
        if clean_text.lower() in DataCleaner.BASIC_INVALID: return None
        
        # --- 平台判定 ---
        # 归一化平台名称，防止数据库里存的是 "jd.com" 或 "京东旗舰店"
        p_str = str(platform_raw).lower() if platform_raw else ""
        is_jd = "京东" in p_str or "jd" in p_str
        
        # --- 策略分支 ---
        
        # 策略A: 长度控制
        # 京东品牌通常规范 (如 "ThinkPad" 较长)，其他平台长品牌多为堆砌
        max_len = 20 if is_jd else 8 
        if len(clean_text) > max_len: 
            return None

        # 策略B: 营销词过滤 (京东豁免，其他严查)
        if not is_jd:
            # 1. 检查营销词
            for bad_word in DataCleaner.MARKETING_INVALID:
                if bad_word in clean_text:
                    return None
            # 2. 检查特殊符号 (淘宝常用【】做修饰)
            if re.search(r'[【】\(\)\[\]（）]', clean_text):
                return None

        return clean_text

    @staticmethod
    def clean_value(text):
        """通用属性值清洗"""
        if not text: return None
        
        # 拍平嵌套字典/列表
        if isinstance(text, dict):
            values = [str(v) for v in text.values() if v and str(v).strip()]
            return ", ".join(values) if values else None
        elif isinstance(text, list):
            return ", ".join([str(v) for v in text if v])
            
        s = str(text).strip()
        if s.lower() in ['无', '未知', 'none', 'null', '', '/', '[]', '{}']:
            return None
        return s

class UnitConverter:
    """单位归一化 (V2.0 宽容模式)"""
    @staticmethod
    def normalize(text):
        if not text: return text
        clean_text = str(text).upper().replace(" ", "")
        
        # 匹配: 数字 + (MM/CM/M/寸)
        pattern = r'(\d+(\.\d+)?)(MM|CM|M|寸)'
        match = re.search(pattern, clean_text)
        
        if not match:
            return text.strip()
            
        value = float(match.group(1))
        unit = match.group(3)
        
        new_value = 0
        if unit == 'MM': new_value = value
        elif unit == 'CM': new_value = value * 10
        elif unit == 'M': new_value = value * 1000
        elif unit == '寸': new_value = value * 33.33
            
        return f"{int(new_value)}mm"

class GraphEngine:
    def __init__(self, db_manager):
        self.db = db_manager

    def _get_node(self, ntype, name, props=None):
        if not name: return None
        clean_name = str(name).strip()
        if not clean_name: return None
        
        ukey = f"{ntype}:{clean_name}"[:255]
        pjson = json.dumps(props or {}, ensure_ascii=False)
        
        with self.db.conn.cursor() as cur:
            cur.execute(f"""
                INSERT INTO {TABLE_NODES} (node_type, name, properties, unique_key)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (unique_key) DO UPDATE SET properties = excluded.properties
                RETURNING id;
            """, (ntype, clean_name, pjson, ukey))
            return cur.fetchone()[0]

    def _add_edge(self, sid, tid, rel):
        if not sid or not tid: return
        with self.db.conn.cursor() as cur:
            cur.execute(f"""
                INSERT INTO {TABLE_EDGES} (source_id, target_id, relation)
                VALUES (%s, %s, %s) ON CONFLICT DO NOTHING
            """, (sid, tid, rel))

    def process_record(self, rec, data):
        # 1. SKU 节点
        sku_props = {"title": rec['title'], "price": str(rec['price']), "url": rec['detail_url']}
        sku_id = self._get_node("SKU", rec['sku'], sku_props)
        
        # 2. 需求关联
        req_id = self._get_node("Requirement", str(rec['procurement_id']))
        self._add_edge(sku_id, req_id, "MATCHES_REQ")
        
        # 3. 平台关联 (直接读取数据库字段)
        platform_val = rec.get('platform') # 从数据库行中获取
        if platform_val:
            # 统一一下平台名称显示 (可选，为了图谱好看)
            p_name = str(platform_val).strip()
            plt_id = self._get_node("Platform", p_name)
            self._add_edge(sku_id, plt_id, "SOLD_ON")

        # 4. 属性处理 (差异化清洗)
        schema_map = {
            "品牌": ("Brand",    "HAS_BRAND",    False),
            "材质": ("Material", "HAS_MATERIAL", False),
            "规格": ("Spec",     "HAS_SPEC",     True),
            "尺寸": ("Size",     "HAS_SIZE",     True),
            "颜色": ("Color",    "HAS_COLOR",    False),
            "型号": ("Model",    "HAS_MODEL",    False),
            "适用对象": ("Target", "FOR_USER",   False),
            "数量": ("Quantity", "HAS_QUANTITY", False)
        }

        for key, raw_val in data.items():
            if key not in schema_map: continue
            
            # === STEP 1: 清洗 (传入 platform_val) ===
            val_to_process = raw_val
            
            if key == "品牌":
                # 关键：传入平台字段，触发差异化逻辑
                val_to_process = DataCleaner.clean_brand(raw_val, platform_val)
            else:
                val_to_process = DataCleaner.clean_value(raw_val)
                
            if not val_to_process: continue

            # === STEP 2: 处理 ===
            node_type, relation, need_norm = schema_map[key]
            
            # 拆分
            vals = re.split(r'[，,、\s]+', val_to_process)
            
            for v in vals:
                clean_v = v.strip()
                if not clean_v: continue
                if clean_v.lower() in ['无', '未知', 'null']: continue

                # 归一化
                if need_norm:
                    final_val = UnitConverter.normalize(clean_v)
                    attr_id = self._get_node(node_type, final_val)
                    self._add_edge(sku_id, attr_id, relation)
                    
                    if final_val != clean_v:
                        orig_id = self._get_node("OriginalSpec", clean_v)
                        self._add_edge(sku_id, orig_id, "HAS_ORIG_SPEC")
                else:
                    attr_id = self._get_node(node_type, clean_v)
                    self._add_edge(sku_id, attr_id, relation)