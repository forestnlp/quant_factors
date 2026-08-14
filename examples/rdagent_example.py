"""
RD-Agent 因子自动挖掘示例

演示如何使用 RD-Agent 进行自动化因子挖掘
"""

import os
import sys
from pathlib import Path

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))


def run_rdagent_factor_loop():
    """
    运行 RD-Agent 因子挖掘循环
    
    注意：需要配置 OpenAI API 密钥
    """
    print("=" * 60)
    print("RD-Agent 自动化因子挖掘")
    print("=" * 60)
    
    # 检查环境变量
    openai_key = os.getenv("OPENAI_API_KEY")
    if not openai_key or openai_key == "your_openai_api_key_here":
        print("\n⚠ 警告：未配置 OpenAI API 密钥")
        print("请设置环境变量:")
        print("  1. 复制 .env.example 到 .env")
        print("  2. 在 .env 中设置 OPENAI_API_KEY")
        print("  3. 或使用：set OPENAI_API_KEY=your_key")
        print("\n如果不使用 RD-Agent，可以跳过此步骤")
        return False
    
    try:
        from rdagent.scenarios.qlib.experiment.factor_experiment import FactorExperiment
        from rdagent.utils.env import QlibEnv
        
        print("\n✓ RD-Agent 导入成功")
        
        # 创建实验
        print("\n创建因子挖掘实验...")
        experiment = FactorExperiment()
        
        print("✓ 实验创建成功")
        print("\nRD-Agent 将自动执行以下流程:")
        print("  1. 分析现有因子和策略表现")
        print("  2. 提出新的因子假设")
        print("  3. 实现因子代码")
        print("  4. 执行回测验证")
        print("  5. 分析结果并迭代优化")
        
        return True
        
    except ImportError as e:
        print(f"\n✗ RD-Agent 导入失败：{e}")
        print("  请确保已安装 RD-Agent:")
        print("  pip install git+https://github.com/microsoft/rd-agent.git")
        return False
    except Exception as e:
        print(f"\n✗ 发生错误：{e}")
        return False


def manual_factor_iteration():
    """
    手动因子迭代示例
    
    如果不使用 RD-Agent，可以手动进行因子迭代
    """
    print("\n" + "=" * 60)
    print("手动因子迭代流程")
    print("=" * 60)
    
    print("\n因子开发流程:")
    print("\n1. 因子提出")
    print("   - 分析市场特征")
    print("   - 提出因子假设")
    print("   - 参考学术文献或业界实践")
    
    print("\n2. 因子实现")
    print("   - 在 src/factor_base.py 中定义因子")
    print("   - 继承 FactorBase 类")
    print("   - 实现 calculate 方法")
    
    print("\n3. 因子检验")
    print("   - IC 分析 (信息系数)")
    print("   - 换手率分析")
    print("   - 因子分层回测")
    
    print("\n4. 因子组合")
    print("   - 多因子加权")
    print("   - 机器学习模型融合")
    
    print("\n5. 策略回测")
    print("   - 完整回测流程")
    print("   - 风险评估")
    print("   - 绩效分析")
    
    print("\n详细示例请参考 examples/advanced_backtest.py")


if __name__ == "__main__":
    print("\nRD-Agent 使用示例")
    print("-" * 60)
    
    # 尝试运行 RD-Agent
    success = run_rdagent_factor_loop()
    
    # 显示手动流程
    if not success:
        print("\n" + "=" * 60)
        print("建议使用手动因子开发流程")
        print("=" * 60)
    
    manual_factor_iteration()
