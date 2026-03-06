# check_current_status.py
import subprocess
import torch
import sys

print("🔍 【关键诊断】你的当前状态：")
print("=" * 50)

# 1. GPU硬件检测
print("1️⃣ NVIDIA显卡状态：")
try:
    result = subprocess.run(['nvidia-smi'], 
                          capture_output=True, text=True, shell=True)
    if result.returncode == 0:
        print("✅ NVIDIA显卡正常工作")
        # 提取关键信息
        lines = result.stdout.split('\n')
        if len(lines) > 8:
            print(f"  显卡型号: {lines[2]}")
            print(f"  驱动版本: {lines[3]}")
            print(f"  CUDA版本: {lines[8] if len(lines) > 8 else '未知'}")
    else:
        print("❌ nvidia-smi命令失败，请分享错误信息：")
        print(result.stderr[:200])
except Exception as e:
    print(f"❌ 无法执行nvidia-smi: {e}")

# 2. PyTorch GPU检测
print("\n2️⃣ PyTorch检测：")
try:
    if torch.cuda.is_available():
        print(f"✅ PyTorch检测到GPU: {torch.cuda.get_device_name(0)}")
        print(f"  可用显存: {torch.cuda.get_device_properties(0).total_memory/1024**3:.1f} GB")
        print(f"  CUDA版本: {torch.version.cuda}")
    else:
        print("❌ PyTorch未检测到CUDA GPU")
except ImportError:
    print("❌ PyTorch未安装")

# 3. Ollama当前状态
print("\n3️⃣ Ollama当前状态：")
try:
    result = subprocess.run(['ollama', 'ps'], 
                          capture_output=True, text=True, shell=True)
    if 'qwen' in result.stdout.lower():
        print("✅ Ollama正在运行（查看是否提到GPU）：")
        if 'gpu' in result.stdout.lower():
            print("  ⭐ Ollama已使用GPU")
        else:
            print("  ⚠️ Ollama可能在使用CPU")
        print(result.stdout[:300])  # 只显示前300字符
    else:
        print("❌ Ollama未运行或没有Qwen模型加载")
except:
    print("❌ 无法检查Ollama状态（Ollama可能未运行）")

# 4. 已安装的Ollama模型检查
print("\n4️⃣ 已安装的模型检查：")
try:
    result = subprocess.run(['ollama', 'list'], 
                          capture_output=True, text=True, shell=True)
    print("已安装的模型：")
    print(result.stdout)
except:
    print("❌ 无法获取模型列表")

print("\n" + "=" * 50)
print("📋 请将以上输出完整复制给我！")
print("有了这4点信息，我能100%确定解决方案")
