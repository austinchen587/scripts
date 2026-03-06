# project_category_classifier.py
"""
项目分类器 - 确保严格返回7个分类之一
分类体系（严格限定）：
1. 行政办公耗材
2. 清洁日化用品  
3. 数码家电
4. 体育器材与服装
5. 专业设备与工业品
6. 食品与饮品
7. 服务与其他
"""

import re
from typing import Dict, List, Tuple, Optional
from llm_client import call_qwen3

class ProjectCategoryClassifier:
    """项目分类器 - 严格限定7个分类"""
    
    # 严格定义的7个分类
    CATEGORIES = {
        "office_supplies": "行政办公耗材",
        "cleaning_chemicals": "清洁日化用品", 
        "digital_appliances": "数码家电",
        "sports_equipment": "体育器材与服装",
        "professional_equipment": "专业设备与工业品",
        "food_beverage": "食品与饮品",
        "services_other": "服务与其他"
    }
    
    # 分类映射反向查找（用于验证）
    CATEGORY_NAME_TO_ID = {v: k for k, v in CATEGORIES.items()}
    
    # 严格限定的分类列表
    VALID_CATEGORIES = list(CATEGORIES.values())
    
    def __init__(self, use_llm: bool = True, confidence_threshold: float = 0.3):
        """
        初始化分类器
        
        Args:
            use_llm: 是否使用LLM进行最终分类
            confidence_threshold: 置信度阈值，低于此值使用LLM
        """
        self.use_llm = use_llm
        self.confidence_threshold = confidence_threshold
        
        # 初始化关键词和规则
        self._init_keywords()
        self._init_rules()
    
    def _init_keywords(self):
        """初始化关键词映射"""
        self.CATEGORY_KEYWORDS = {
            "office_supplies": [
                "打印纸", "复印纸", "文具", "笔", "文件夹", "文件袋", "档案盒", "档案柜",
                "订书机", "胶水", "固体胶", "回形针", "大头针", "笔记本", "便签纸",
                "文件柜", "密集架", "货架", "办公耗材", "办公用品", "A4", "A3", "打印耗材",
                "硒鼓", "墨盒", "碳粉", "复印机", "碎纸机", "装订机", "打孔机", "计算器",
                "尺子", "圆规", "橡皮", "修正液", "笔筒", "名片盒", "印章", "印泥"
            ],
            "cleaning_chemicals": [
                "洗衣液", "洗手液", "洗洁精", "消毒液", "洁厕剂", "抽纸", "卷纸", "纸巾",
                "湿巾", "面巾纸", "垃圾袋", "油污清洁剂", "消毒剂", "免洗手", "酒精",
                "84消毒液", "洗涤", "清洁", "去污", "清新剂", "柔顺剂", "消毒水", "漂白水",
                "空气清新剂", "杀虫剂", "除螨剂", "洁厕宝", "管道疏通剂", "玻璃清洁剂",
                "地板蜡", "家具蜡", "洗衣粉", "肥皂", "香皂", "沐浴露", "洗发水", "护发素"
            ],
            "digital_appliances": [
                # 电脑与配件
                "电脑", "台式机", "平板", "平板电脑", "笔记本", "计算机", "显示器",
                "鼠标", "键盘", "耳机", "耳麦", "摄像头", "摄像头", "U盘", "硬盘",
                "移动硬盘", "固态硬盘", "内存条", "显卡", "主板", "CPU", "机箱", "电源",
                "散热器", "光驱", "刻录机", "声卡", "网卡", "蓝牙", "适配器", "扩展坞",
                # 网络设备
                "路由器", "交换机", "光纤", "收发器", "网线", "水晶头", "配线架",
                "网卡", "无线网卡", "4G路由器", "5G路由器", "网络存储", "NAS",
                # 家电
                "空调", "微波炉", "冰箱", "冰柜", "电磁炉", "电饭煲", "电压力锅",
                "电热水器", "电炸锅", "电炖锅", "电火锅", "电风扇", "吸顶扇",
                "榨汁机", "破壁机", "豆浆机", "搅拌机", "电水壶", "保温壶",
                "电吹风", "挂烫机", "电熨斗", "加湿器", "除湿机", "空气净化器",
                "净水器", "饮水机", "电烤箱", "电饼铛", "电蒸锅", "电烤炉",
                # 办公设备（电子类）
                "打印机", "扫描仪", "投影仪", "传真机", "复印机", "一体机",
                "电子白板", "视频会议", "电话机", "对讲机", "考勤机", "门禁机",
                # 数码产品
                "相机", "摄像机", "DV", "单反", "微单", "镜头", "闪光灯", "三脚架",
                "云台", "稳定器", "录音笔", "MP3", "MP4", "播放器", "游戏机",
                # 其他电子
                "电子钟", "电子秤", "电子血压计", "电子体温计", "电子按摩器"
            ],
            "sports_equipment": [
                # 体育器材
                "排球", "羽毛球", "篮球", "足球", "乒乓球", "体操垫", "运动垫",
                "健身器材", "训练器材", "体育器材", "体育用品", "运动器材",
                "网球", "台球", "保龄球", "高尔夫", "毽子", "跳绳", "哑铃",
                "杠铃", "拉力器", "臂力器", "握力器", "腹肌轮", "瑜伽球",
                "蹦床", "跳箱", "鞍马", "单杠", "双杠", "平衡木", "跳高架",
                "跨栏架", "起跑器", "秒表", "口哨", "记分牌", "标志杆",
                # 服装鞋类
                "运动服", "运动鞋", "健身服", "训练服", "体育服装", "运动服装",
                "羽绒服", "冲锋衣", "保暖服", "棉衣", "运动袜", "瑜伽服",
                "泳衣", "泳裤", "泳帽", "泳镜", "潜水镜", "滑雪服", "滑雪板",
                "滑冰鞋", "轮滑鞋", "护具", "护膝", "护肘", "头盔", "手套",
                "运动背包", "水壶", "毛巾", "头巾", "发带",
                # 品牌相关
                "李宁", "安踏", "特步", "乔丹", "耐克", "阿迪", "匹克", "鸿星尔克",
                "361度", "匡威", "新百伦", "亚瑟士", "美津浓", "斯凯奇", "斐乐"
            ],
            "professional_equipment": [
                # 工程机械与设备
                "发电机组", "发电机", "柴油机", "水泵", "排污泵", "清洗设备",
                "高压洗车机", "压缩机", "空压机", "电焊机", "切割机",
                "挖掘机", "装载机", "推土机", "起重机", "吊车", "叉车",
                "压路机", "摊铺机", "搅拌机", "打桩机", "夯土机", "破碎机",
                "筛分机", "输送机", "提升机", "卷扬机", "绞车", "千斤顶",
                # 消防安防
                "消防", "灭火器", "消防栓", "消防水带", "消防面具", "防毒面具",
                "呼吸器", "逃生面具", "应急灯", "安全出口", "警示灯", "爆闪灯",
                "反光背心", "反光锥", "安全帽", "防护服", "防护手套", "防护鞋",
                "护目镜", "耳塞", "安全绳", "安全带", "安全网", "警戒线",
                "监控", "摄像头", "录像机", "报警器", "门禁", "对讲", "巡更",
                "安检", "防爆", "防雷", "接地", "避雷针",
                # 实验室与测量
                "电子天平", "分析天平", "测温仪", "额温枪", "血压计", "测量仪",
                "检测仪", "气体检测", "酒精检测", "钢筋扫描", "测绘仪器",
                "显微镜", "离心机", "振荡器", "培养箱", "干燥箱", "灭菌器",
                "PH计", "电导率仪", "分光光度计", "色谱仪", "光谱仪", "质谱仪",
                "试验机", "硬度计", "探伤仪", "测厚仪", "粗糙度仪", "圆度仪",
                # 专业工具
                "电表", "电度表", "阀门", "锁具", "工具箱", "维修工具", "电动工具",
                "手电筒", "照明灯", "探照灯", "三脚架", "摄像机", "相机",
                "电钻", "电锤", "角磨机", "切割机", "热风枪", "电烙铁",
                "万用表", "示波器", "信号发生器", "电源", "电池", "充电器",
                # 医疗设备
                "病床", "轮椅", "担架", "输液架", "监护仪", "呼吸机", "麻醉机",
                "手术灯", "手术台", "消毒器", "灭菌器", "超声波", "X光", "CT",
                "MRI", "心电图", "脑电图", "B超", "内窥镜", "显微镜",
                # 其他专业设备
                "音响设备", "音频", "话筒", "麦克风", "调音台", "功放", "音箱",
                "灯光设备", "舞台灯光", "LED屏", "显示屏", "大屏", "触摸屏",
                "广播系统", "会议系统", "表决系统", "同传系统", "翻译系统",
                "厨房设备", "厨具", "灶具", "餐具", "炊具", "烘焙设备",
                "洗衣设备", "烘干机", "熨平机", "折叠机",
                "清洁设备", "扫地机", "洗地机", "吸尘器", "高压清洗机"
            ],
            "food_beverage": [
                "食品", "饮料", "牛奶", "矿泉水", "纯净水", "山茶油", "橄榄油",
                "菜籽油", "大米", "面粉", "面条", "饼干", "面包", "蛋糕",
                "糖果", "巧克力", "坚果", "炒货", "零食", "方便面", "粉丝",
                "米线", "火腿肠", "香肠", "腊肉", "茶叶", "咖啡", "果汁",
                "奶茶", "酸奶", "奶酪", "黄油", "蜂蜜", "果酱", "沙拉酱",
                "调味品", "酱油", "醋", "盐", "糖", "味精", "鸡精", "料酒",
                "花椒", "八角", "桂皮", "香叶", "辣椒", "胡椒", "孜然",
                "速冻食品", "水饺", "汤圆", "包子", "馒头", "花卷", "烧卖",
                "豆制品", "豆腐", "豆浆", "豆干", "腐竹", "豆皮",
                "肉类", "猪肉", "牛肉", "羊肉", "鸡肉", "鸭肉", "鱼肉",
                "蔬菜", "水果", "苹果", "香蕉", "梨", "橙子", "橘子", "葡萄",
                "西瓜", "草莓", "蓝莓", "樱桃", "桃子", "李子", "杏子",
                # 品牌
                "蒙牛", "伊利", "光明", "君乐宝", "三元", "完达山",
                "金龙鱼", "福临门", "鲁花", "多力", "长寿花",
                "农夫山泉", "娃哈哈", "康师傅", "统一", "可口可乐", "百事可乐",
                "王老吉", "加多宝", "红牛", "东鹏特饮", "脉动", "激活"
            ],
            "services_other": [
                "维修", "保养", "安装", "调试", "服务", "软件", "系统", "授权",
                "管理软件", "技术服务", "维修服务", "安装服务", "调试服务",
                "培训", "咨询", "设计", "规划", "监理", "检测", "检验",
                "认证", "评估", "审计", "会计", "法律", "广告", "宣传",
                "印刷", "出版", "制作", "拍摄", "录制", "编辑", "翻译",
                "租赁", "外包", "代理", "招标", "投标", "采购", "物流",
                "运输", "仓储", "配送", "快递", "物业", "保安", "保洁",
                "绿化", "养护", "拆除", "改造", "装修", "装饰", "施工",
                "工程", "建设", "开发", "研究", "调查", "统计", "分析"
            ]
        }
    
    def _init_rules(self):
        """初始化分类规则"""
        # 品牌到分类的映射
        self.BRAND_CATEGORY_MAPPING = {
            # 数码家电品牌
            "联想": "digital_appliances", "华为": "digital_appliances",
            "苹果": "digital_appliances", "戴尔": "digital_appliances",
            "惠普": "digital_appliances", "华硕": "digital_appliances",
            "宏碁": "digital_appliances", "小米": "digital_appliances",
            "荣耀": "digital_appliances", "三星": "digital_appliances",
            "索尼": "digital_appliances", "松下": "digital_appliances",
            "飞利浦": "digital_appliances", "美的": "digital_appliances",
            "格力": "digital_appliances", "海尔": "digital_appliances",
            "海信": "digital_appliances", "TCL": "digital_appliances",
            "创维": "digital_appliances", "长虹": "digital_appliances",
            "康佳": "digital_appliances", "奥克斯": "digital_appliances",
            "九阳": "digital_appliances", "苏泊尔": "digital_appliances",
            "格兰仕": "digital_appliances", "奔腾": "digital_appliances",
            
            # 体育品牌
            "李宁": "sports_equipment", "安踏": "sports_equipment",
            "特步": "sports_equipment", "乔丹": "sports_equipment",
            "耐克": "sports_equipment", "阿迪达斯": "sports_equipment",
            "匹克": "sports_equipment", "鸿星尔克": "sports_equipment",
            "361度": "sports_equipment", "匡威": "sports_equipment",
            "新百伦": "sports_equipment", "亚瑟士": "sports_equipment",
            "美津浓": "sports_equipment", "斯凯奇": "sports_equipment",
            "斐乐": "sports_equipment", "卡帕": "sports_equipment",
            
            # 清洁日化品牌
            "蓝月亮": "cleaning_chemicals", "立白": "cleaning_chemicals",
            "超能": "cleaning_chemicals", "雕牌": "cleaning_chemicals",
            "奥妙": "cleaning_chemicals", "汰渍": "cleaning_chemicals",
            "碧浪": "cleaning_chemicals", "威猛先生": "cleaning_chemicals",
            "心相印": "cleaning_chemicals", "维达": "cleaning_chemicals",
            "清风": "cleaning_chemicals", "洁柔": "cleaning_chemicals",
            "舒肤佳": "cleaning_chemicals", "六神": "cleaning_chemicals",
            "潘婷": "cleaning_chemicals", "海飞丝": "cleaning_chemicals",
            "飘柔": "cleaning_chemicals", "清扬": "cleaning_chemicals",
            "沙宣": "cleaning_chemicals", "欧莱雅": "cleaning_chemicals",
            
            # 食品品牌
            "蒙牛": "food_beverage", "伊利": "food_beverage",
            "光明": "food_beverage", "君乐宝": "food_beverage",
            "三元": "food_beverage", "完达山": "food_beverage",
            "金龙鱼": "food_beverage", "福临门": "food_beverage",
            "鲁花": "food_beverage", "多力": "food_beverage",
            "长寿花": "food_beverage", "农夫山泉": "food_beverage",
            "娃哈哈": "food_beverage", "康师傅": "food_beverage",
            "统一": "food_beverage", "可口可乐": "food_beverage",
            "百事可乐": "food_beverage", "王老吉": "food_beverage",
            "加多宝": "food_beverage", "红牛": "food_beverage",
            "东鹏特饮": "food_beverage", "脉动": "food_beverage",
            "三只松鼠": "food_beverage", "良品铺子": "food_beverage",
            "百草味": "food_beverage", "来伊份": "food_beverage",
            
            # 办公品牌
            "得力": "office_supplies", "齐心": "office_supplies",
            "晨光": "office_supplies", "真彩": "office_supplies",
            "爱好": "office_supplies", "白雪": "office_supplies",
            "天章": "office_supplies", "亚太森博": "office_supplies",
            "Double A": "office_supplies", "百旺": "office_supplies",
            "金旗舰": "office_supplies", "科密": "office_supplies",
            
            # 专业设备品牌
            "奔图": "professional_equipment", "兄弟": "professional_equipment",
            "震旦": "professional_equipment", "爱普生": "professional_equipment",
            "佳能": "professional_equipment", "理光": "professional_equipment",
            "施乐": "professional_equipment", "京瓷": "professional_equipment",
            "柯尼卡美能达": "professional_equipment", "夏普": "professional_equipment",
            "松下": "professional_equipment", "索尼": "professional_equipment",
            "铁三角": "professional_equipment", "舒尔": "professional_equipment",
            "森海塞尔": "professional_equipment", "博世": "professional_equipment",
            "海康威视": "professional_equipment", "大华": "professional_equipment",
            "宇视": "professional_equipment", "华为": "professional_equipment",
            "华三": "professional_equipment", "锐捷": "professional_equipment",
            "中兴": "professional_equipment", "思科": "professional_equipment",
            "TP-LINK": "professional_equipment", "腾达": "professional_equipment",
            "水星": "professional_equipment", "迅捷": "professional_equipment"
        }
        
        # 强制分类规则（特定关键词必须归入特定分类）
        self.FORCE_CATEGORY_RULES = {
            # 关键词: (强制分类ID, 权重)
            "维修": ("services_other", 10.0),
            "保养": ("services_other", 10.0),
            "安装": ("services_other", 10.0),
            "服务": ("services_other", 10.0),
            "软件": ("services_other", 10.0),
            "系统": ("services_other", 10.0),
            "授权": ("services_other", 10.0),
            
            "电脑": ("digital_appliances", 5.0),
            "计算机": ("digital_appliances", 5.0),
            "笔记本": ("digital_appliances", 5.0),
            "平板": ("digital_appliances", 5.0),
            
            "空调": ("digital_appliances", 5.0),
            "冰箱": ("digital_appliances", 5.0),
            "洗衣机": ("digital_appliances", 5.0),
            
            "食品": ("food_beverage", 10.0),
            "饮料": ("food_beverage", 10.0),
            "牛奶": ("food_beverage", 10.0),
            "粮油": ("food_beverage", 10.0),
            
            "体育": ("sports_equipment", 10.0),
            "运动": ("sports_equipment", 8.0),
            "健身": ("sports_equipment", 8.0),
            
            "消防": ("professional_equipment", 10.0),
            "安防": ("professional_equipment", 10.0),
            "工程": ("professional_equipment", 8.0),
            "机械": ("professional_equipment", 8.0),
            
            "办公": ("office_supplies", 5.0),
            "文具": ("office_supplies", 8.0),
            "纸张": ("office_supplies", 8.0),
            
            "清洁": ("cleaning_chemicals", 8.0),
            "消毒": ("cleaning_chemicals", 8.0),
            "洗涤": ("cleaning_chemicals", 8.0),
        }
    
    def classify_project(self, project_name: str, commodity_names: List[str] = None,
                        description: str = "", suggested_brands: List[str] = None) -> str:
        """
        分类项目 - 严格限定7个分类
        
        Args:
            project_name: 项目名称
            commodity_names: 商品名称列表
            description: 项目描述
            suggested_brands: 建议品牌列表
            
        Returns:
            严格限定的7个分类之一
        """
        try:
            # 1. 提取分析文本
            text_for_analysis = self._extract_analysis_text(
                project_name, commodity_names, description, suggested_brands
            )
            
            # 2. 基于规则分类
            category_id, confidence = self._classify_by_rules(text_for_analysis)
            
            # 3. 如果置信度低或初始分类是"其他"，使用LLM
            if (self.use_llm and confidence < self.confidence_threshold) or category_id == "services_other":
                llm_category = self._classify_with_llm(
                    project_name, commodity_names, description, category_id
                )
                # 验证LLM返回的分类是否在7个分类内
                validated_category = self._validate_category(llm_category, category_id)
                return validated_category
            else:
                return self.CATEGORIES[category_id]
                
        except Exception as e:
            print(f"分类出错: {e}, 返回默认分类'服务与其他'")
            return "服务与其他"
    
    def _extract_analysis_text(self, project_name: str, commodity_names: List[str],
                              description: str, suggested_brands: List[str]) -> str:
        """提取所有用于分析的文本"""
        analysis_text = project_name.lower()
        
        if commodity_names:
            for name in commodity_names:
                if isinstance(name, str):
                    analysis_text += " " + name.lower()
        
        if description:
            analysis_text += " " + description[:500].lower()
        
        if suggested_brands:
            for brand in suggested_brands:
                if isinstance(brand, str):
                    analysis_text += " " + brand.lower()
        
        return analysis_text
    
    def _classify_by_rules(self, analysis_text: str) -> Tuple[str, float]:
        """
        基于规则分类
        
        Returns:
            (category_id, confidence_score)
        """
        # 初始化分数
        category_scores = {cat_id: 0.0 for cat_id in self.CATEGORIES.keys()}
        
        # 1. 强制规则匹配（最高优先级）
        for keyword, (force_category_id, weight) in self.FORCE_CATEGORY_RULES.items():
            if keyword.lower() in analysis_text:
                category_scores[force_category_id] += weight
        
        # 2. 关键词匹配
        for category_id, keywords in self.CATEGORY_KEYWORDS.items():
            for keyword in keywords:
                if keyword.lower() in analysis_text:
                    category_scores[category_id] += 1.0
        
        # 3. 品牌识别
        for brand, category_id in self.BRAND_CATEGORY_MAPPING.items():
            if brand.lower() in analysis_text:
                category_scores[category_id] += 2.0
        
        # 4. 特殊规则处理
        self._apply_special_rules(analysis_text, category_scores)
        
        # 找到最高分
        max_score = max(category_scores.values())
        if max_score == 0:
            return "services_other", 0.0
        
        max_categories = [cat_id for cat_id, score in category_scores.items() 
                         if score == max_score]
        
        if len(max_categories) == 1:
            category_id = max_categories[0]
            total_score = sum(category_scores.values())
            confidence = max_score / total_score if total_score > 0 else 0.0
            return category_id, min(confidence, 1.0)  # 确保不超过1.0
        else:
            # 多个分类分数相同
            return "services_other", 0.2
    
    def _apply_special_rules(self, analysis_text: str, category_scores: Dict):
        """应用特殊规则"""
        # 规则1：打印机处理
        if "打印机" in analysis_text:
            # 专业打印机品牌 -> 专业设备
            if any(brand in analysis_text for brand in ["奔图", "兄弟", "震旦", "理光"]):
                category_scores["professional_equipment"] += 3.0
            # 家用打印机 -> 数码家电
            else:
                category_scores["digital_appliances"] += 2.0
        
        # 规则2：电脑相关
        if any(word in analysis_text for word in ["电脑", "计算机", "笔记本"]):
            # 联想、华为、戴尔等品牌 -> 数码家电
            if any(brand in analysis_text for brand in ["联想", "华为", "戴尔", "惠普", "华硕"]):
                category_scores["digital_appliances"] += 3.0
                category_scores["professional_equipment"] = max(0, category_scores["professional_equipment"] - 1.0)
        
        # 规则3：空调处理
        if "空调" in analysis_text:
            if any(brand in analysis_text for brand in ["美的", "格力", "海尔", "奥克斯"]):
                category_scores["digital_appliances"] += 3.0
        
        # 规则4：文件柜/密集架处理
        if any(word in analysis_text for word in ["文件柜", "密集架", "档案柜"]):
            category_scores["office_supplies"] += 2.0
        
        # 规则5：实验室设备
        if any(word in analysis_text for word in ["天平", "显微镜", "离心机", "培养箱"]):
            category_scores["professional_equipment"] += 3.0
    
    def _classify_with_llm(self, project_name: str, commodity_names: List[str],
                          description: str, initial_category_id: str) -> str:
        """
        使用LLM进行最终分类
        """
        commodities_str = "、".join(commodity_names) if commodity_names else "无明确商品"
        
        prompt = f"""你是政府采购分类专家。请分析项目并选择**严格属于以下7个分类之一**：

【必须选择的7个分类】（不可选择其他）：
1. 行政办公耗材
2. 清洁日化用品  
3. 数码家电
4. 体育器材与服装
5. 专业设备与工业品
6. 食品与饮品
7. 服务与其他

【项目信息】
项目：{project_name}
商品：{commodities_str}
描述：{description[:300] if description else "无描述"}

【分类规则】：
1. 只能返回上面7个分类名称之一
2. 不要解释，不要添加其他文字
3. 如果难以确定，优先考虑"服务与其他"
4. 电脑、空调、打印机等电器归"数码家电"
5. 消防、工程、实验室设备归"专业设备"
6. 食品粮油归"食品与饮品"
7. 体育用品归"体育器材与服装"
8. 办公用品归"行政办公耗材"
9. 清洁用品归"清洁日化用品"
10. 维修、服务类归"服务与其他"

请严格返回7个分类名称之一："""
        
        try:
            llm_response = call_qwen3(prompt)
            return self._parse_llm_response(llm_response)
        except Exception as e:
            print(f"LLM调用失败: {e}")
            return self.CATEGORIES[initial_category_id]
    
    def _parse_llm_response(self, response: str) -> str:
        """解析LLM响应，确保返回7个分类之一"""
        if not response:
            return "服务与其他"
        
        clean_response = response.strip()
        
        # 直接匹配分类名称
        for category in self.VALID_CATEGORIES:
            if category in clean_response:
                return category
        
        # 数字匹配
        number_map = {
            "1": "行政办公耗材",
            "2": "清洁日化用品",
            "3": "数码家电",
            "4": "体育器材与服装",
            "5": "专业设备与工业品",
            "6": "食品与饮品",
            "7": "服务与其他"
        }
        
        for num, category in number_map.items():
            if num in clean_response:
                return category
        
        # 模糊匹配
        for category in self.VALID_CATEGORIES:
            # 检查是否包含关键部分
            if any(keyword in clean_response for keyword in category.split()):
                return category
        
        # 默认返回"服务与其他"
        return "服务与其他"
    
    def _validate_category(self, category: str, fallback_category_id: str) -> str:
        """验证分类是否在7个分类内"""
        if category in self.VALID_CATEGORIES:
            return category
        else:
            print(f"警告：分类'{category}'不在有效分类中，使用备用分类")
            return self.CATEGORIES.get(fallback_category_id, "服务与其他")


# 严格的分类验证函数
def validate_and_classify(project_name: str, commodity_names: List[str] = None,
                         description: str = "", use_llm: bool = True) -> str:
    """
    严格验证的分类函数
    
    Args:
        project_name: 项目名称
        commodity_names: 商品名称列表
        description: 项目描述
        use_llm: 是否使用LLM
        
    Returns:
        严格限定的7个分类之一
    """
    classifier = ProjectCategoryClassifier(use_llm=use_llm)
    
    # 确保输入参数有效性
    if commodity_names is None:
        commodity_names = []
    
    # 进行分类
    category = classifier.classify_project(
        project_name=project_name,
        commodity_names=commodity_names,
        description=description or "",
        suggested_brands=[]
    )
    
    # 最终验证
    if category not in classifier.VALID_CATEGORIES:
        print(f"严重错误：分类'{category}'不在有效分类中，强制设置为'服务与其他'")
        return "服务与其他"
    
    return category


# 测试函数
def test_strict_classification():
    """测试严格分类"""
    test_cases = [
        # (项目名, 商品名, 期望分类)
        ("洗手液采购", "洗手液", "清洁日化用品"),
        ("电脑采购", "台式电脑", "数码家电"),
        ("体育器材", "篮球、排球", "体育器材与服装"),
        ("食品采购", "大米、食用油", "食品与饮品"),
        ("打印机维修", "打印机维修服务", "服务与其他"),
        ("消防设备", "灭火器、消防栓", "专业设备与工业品"),
        ("办公用品", "打印纸、文件夹", "行政办公耗材"),
        ("实验室设备", "电子天平", "专业设备与工业品"),
        ("空调安装", "空调安装服务", "服务与其他"),
        ("运动服装", "运动服、运动鞋", "体育器材与服装"),
    ]
    
    print("严格分类测试（必须返回7个分类之一）")
    print("=" * 80)
    
    classifier = ProjectCategoryClassifier(use_llm=False)
    
    for project_name, commodity_str, expected in test_cases:
        commodity_names = []
        if commodity_str:
            commodity_names = [name.strip() for name in commodity_str.split('、')]
        
        result = classifier.classify_project(project_name, commodity_names)
        
        # 验证结果是否在7个分类内
        is_valid = result in classifier.VALID_CATEGORIES
        is_correct = result == expected
        
        status = "✓" if is_valid else "✗"
        correctness = "正确" if is_correct else f"错误（期望:{expected}）"
        
        print(f"{status} {project_name}")
        print(f"  商品: {commodity_str}")
        print(f"  结果: {result} - {correctness}")
        if not is_valid:
            print(f"  ⚠️ 分类不在有效列表内！")
        print("-" * 80)


if __name__ == "__main__":
    test_strict_classification()
