# main.py - 修复版：自动启动GPU优化的Ollama服务器
import sys
import os
import subprocess
import time
import time  # 导入 time 模块
from datetime import datetime

# 将当前目录添加到系统路径，确保可以导入 main_pipeline 模块
sys.path.insert(0, os.path.dirname(__file__))

try:
    from main_pipeline.main_controller import MainController
    print("✅ 成功导入 MainController")
except ImportError as e:
    print(f"❌ 导入失败: {e}")
    print(f"当前路径: {os.path.dirname(__file__)}")
    print(f"sys.path: {sys.path}")
    raise

def run_subprocess_with_encoding(cmd, capture=True, timeout=30):
    """运行子进程，处理编码问题"""
    try:
        # Windows上使用UTF-8编码
        env = os.environ.copy()
        # 确保控制台使用UTF-8
        if os.name == 'nt':
            env['PYTHONIOENCODING'] = 'utf-8'
        
        # 【关键】清除代理环境变量，防止影响本地服务
        proxy_keys = ['HTTP_PROXY', 'HTTPS_PROXY', 'http_proxy', 'https_proxy', 'ALL_PROXY', 'all_proxy']
        
        if capture:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding='utf-8',
                errors='ignore',  # 忽略无法解码的字符
                timeout=timeout,
                env=env,
                shell=True if os.name == 'nt' else False
            )
            return result
        else:
            # 不捕获输出，直接运行
            subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                env=env,
                shell=True if os.name == 'nt' else False,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            )
            return None
    except Exception as e:
        print(f"⚠️ 子进程执行失败: {e}")
        return None

def ensure_ollama_gpu_server():
    """确保Ollama以GPU模式运行（自动启动或重启）"""
    
    print("🔧 检查Ollama服务状态...")
    
    # 【关键】设置GPU环境变量
    os.environ['OLLAMA_NUM_GPU'] = '99'  # 尽可能使用GPU层
    os.environ['CUDA_VISIBLE_DEVICES'] = '0'  # 使用第一个GPU
    os.environ['OLLAMA_FLASH_ATTENTION'] = '1'  # 启用Flash Attention加速
    
    # 1. 尝试连接现有服务
    try:
        import requests
        response = requests.get('http://127.0.0.1:11434/api/tags', timeout=2, proxies={})
        if response.status_code == 200:
            print("✅ Ollama服务已运行")
            
            # 检查是否使用GPU
            try:
                ps_result = run_subprocess_with_encoding(['ollama', 'ps'])
                if ps_result and ps_result.returncode == 0:
                    if 'gpu' in ps_result.stdout.lower():
                        print("⭐ Ollama正在使用GPU加速")
                        return True
                    else:
                        print("⚠️ Ollama可能在CPU模式运行，尝试重启为GPU模式...")
                        return restart_ollama_for_gpu()
            except:
                print("📡 无法检查服务详情，继续执行...")
                return True
            return True
    except:
        print("❌ Ollama服务未运行或无法连接")
    
    # 2. 启动Ollama服务
    print("🚀 启动GPU优化的Ollama服务...")
    return restart_ollama_for_gpu()

def restart_ollama_for_gpu():
    """重启Ollama为GPU模式"""
    
    # 停止现有进程
    try:
        print("🛑 停止现有Ollama进程...")
        # Windows
        if os.name == 'nt':
            run_subprocess_with_encoding(['taskkill', '/F', '/IM', 'ollama.exe'])
        # Linux/Mac
        else:
            run_subprocess_with_encoding(['pkill', '-f', 'ollama serve'])
        time.sleep(2)
    except:
        pass
    
    # 启动Ollama（后台模式）
    try:
        print("🎯 启动GPU优化的Ollama服务...")
        
        # 后台启动，不捕获输出
        run_subprocess_with_encoding(['ollama', 'serve'], capture=False)
        
    except Exception as e:
        print(f"❌ 启动Ollama失败: {e}")
        print("⚠️ 请手动命令行执行: ollama serve")
        return False
    
    # 等待服务就绪
    print("⏳ 等待Ollama服务启动...")
    for i in range(10):  # 最多等待10秒
        try:
            import requests
            requests.get('http://127.0.0.1:11434/', timeout=1,proxies={})
            print(f"✅ Ollama服务准备就绪 ({i+1}秒)")
            break
        except:
            print(f"  等待... {i+1}s")
            time.sleep(1)
    
    # 确保模型就绪
    time.sleep(2)
    
    # 检查服务状态
    print("🤖 检查模型加载状态（GPU模式）...")
    try:
        # 只检查服务是否可用，不关心输出
        import requests
        models_resp = requests.get('http://127.0.0.1:11434/api/tags', timeout=5,proxies={})
        if models_resp.status_code == 200:
            print("✅ Ollama服务运行正常")
            
            # 尝试更简单地检查GPU状态
            try:
                # 直接查询模型信息，避免子进程编码问题
                payload = {
                    "model": "qwen3:8b",
                    "prompt": "ping",
                    "stream": False
                }
                response = requests.post('http://127.0.0.1:11434/api/generate', 
                                       json=payload, timeout=10,proxies={})
                if response.status_code == 200:
                    print("✅ Qwen3模型响应正常")
                    return True
            except:
                print("⚠️ 模型检查跳过，服务可能已启动")
                return True
        else:
            print("⚠️ 服务检查异常，但继续尝试...")
            return True  # 服务器可能已启动
    except Exception as e:
        print(f"⚠️ 服务检查异常: {e}")
        return True  # 返回True让主流程继续尝试

def create_gpu_model_config():
    """创建GPU优化模型配置（备用方案）"""
    
    config_file = 'qwen3_gpu.ModelFile'
    
    gpu_config = """FROM qwen3:8b

# GPU配置优化
PARAMETER num_gpu 99        # 使用尽可能多的GPU层
PARAMETER num_thread 0      # 自动决定线程数  
PARAMETER num_ctx 4096      # 上下文长度
PARAMETER temperature 0.1   # 稳定性优先
"""
    
    try:
        with open(config_file, 'w', encoding='utf-8') as f:
            f.write(gpu_config)
        
        print(f"📄 创建GPU优化配置: {config_file}")
        
        # 创建新的GPU优化模型
        result = run_subprocess_with_encoding(['ollama', 'create', 'qwen3:8b-gpu', '-f', config_file])
        
        if result and result.returncode == 0:
            print("✅ 创建GPU优化模型成功")
            os.environ['LLM_MODEL'] = 'qwen3:8b-gpu'
        else:
            print(f"⚠️ GPU模型创建失败")
            if result:
                print(f"  错误: {result.stderr[:100]}")
            
    except Exception as e:
        print(f"⚠️ 创建GPU配置失败: {e}")

def wait_for_gpu_initialization():
    """等待GPU完全初始化（避免首次调用超时）"""
    
    print("🔋 等待GPU推理引擎准备就绪...")
    
    try:
        # 简单的预热调用
        import requests
        import json
        
        warmup_payload = {
            "model": "qwen3:8b",
            "prompt": "你好，这是一个测试。",
            "stream": False,
            "temperature": 0.1,
            "max_tokens": 10
        }
        
        for attempt in range(3):
            try:
                response = requests.post(
                    'http://127.0.0.1:11434/api/generate',
                    json=warmup_payload,
                    timeout=30,
                    proxies={}
                )
                if response.status_code == 200:
                    print(f"✅ GPU推理引擎预热成功 ({attempt+1})")
                    return
            except requests.exceptions.Timeout:
                print(f"🔥 GPU首次推理准备中... ({attempt+1}/3)")
                time.sleep(5)
    except:
        print("⚠️ 预热跳过，直接继续...")
        time.sleep(3)




def main():
    """主函数 - 循环守护模式"""
    print("=" * 60)
    print("🚀 启动政府采购商品智能解析系统 (守护模式: 2小时轮询)")
    print("=" * 60)

    # ... (保持原有的 GPU 检查和预热逻辑不变) ...
    # if not ensure_ollama_gpu_server(): ...
    # wait_for_gpu_initialization() ...

    # === 进入无限循环 ===
    while True:
        cycle_start_time = datetime.now()
        print(f"\n[SYSTEM] 🕒 开始新一轮任务循环: {cycle_start_time.strftime('%Y-%m-%d %H:%M:%S')}")
        
        try:
            # 1. 实例化控制器 (每次循环新建，确保DB连接是新鲜的)
            # 注意：cleanup_files=True 会在处理完后删除下载的文件，节省空间
            controller = MainController(batch_size=10, skip_processed=True, cleanup_files=True)
            
            # 2. 执行批量处理任务
            controller.run()
            
            # 3. 显式关闭连接 (虽然 controller 析构时可能会关，但显式调用更安全)
            if hasattr(controller, 'db_writer') and controller.db_writer:
                controller.db_writer.close()
                
            print(f"[SYSTEM] ✅ 本轮任务处理完毕")

        except Exception as e:
            print(f"[SYSTEM] ❌ 本轮任务发生异常 (将自动进入休眠): {e}")
            import traceback
            traceback.print_exc()
        
        # === 静默休眠逻辑 ===
        sleep_hours = 2
        sleep_seconds = sleep_hours * 60 * 60
        
        next_run_time = datetime.fromtimestamp(time.time() + sleep_seconds)
        print(f"\n[SYSTEM] 💤 进入静默休眠状态 {sleep_hours} 小时...")
        print(f"[SYSTEM] ⏰ 下次唤醒时间: {next_run_time.strftime('%Y-%m-%d %H:%M:%S')}")
        print("=" * 60)
        
        # 开始休眠
        time.sleep(sleep_seconds)

if __name__ == "__main__":
    main()