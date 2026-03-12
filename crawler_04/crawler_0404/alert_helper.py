# alert_helper.py
import winsound
import time
from logger_helper import logger
# [新增] 引入浏览器池，用于状态复查
from browser_manager import pool 

def urgent_pause(platform_name, browser_name):
    """
    遇到验证码：报警 -> 暂停 -> 人工处理 -> [关键] 全局环境复查 -> 恢复
    """
    logger.error("="*50)
    logger.error(f"🚨🚨🚨 [严重警告] {platform_name} ({browser_name}) 遇到验证码！")
    logger.error("🛑 脚本已挂起！请前往对应窗口手动处理！")
    logger.error("👉 处理标准：滑动验证码/扫码登录 -> 直到页面恢复为商品搜索列表")
    logger.error("="*50)

    # 1. 报警音
    try:
        for _ in range(3):
            winsound.Beep(1000, 500)
            time.sleep(0.5)
    except: pass

    # 2. 循环确认逻辑
    while True:
        input(f">> ✅ 手动处理完毕后，请在控制台按 [回车键] 申请复查...")
        
        logger.info("🔍 [System] 正在复查所有浏览器状态...")
        
        # 调用 browser_manager 中的检查方法
        all_ready, not_ready_list = pool.check_all_browsers_ready()
        
        if all_ready:
            logger.info("✅ [复查通过] 所有浏览器均已就绪！")
            logger.info("🚀 3秒后恢复执行...")
            time.sleep(3)
            break
        else:
            logger.error("="*50)
            logger.error(f"❌ [复查失败] 以下浏览器仍未进入搜索状态: {not_ready_list}")
            logger.error("👉 请确保所有打开的浏览器窗口，都停留在关键词搜索结果页面！")
            logger.error("👉 请继续处理，处理完再次按回车。")
            logger.error("="*50)
            # 再次报警提示
            try: winsound.Beep(500, 300)
            except: pass