"""
Qlib 基础回测示例

演示如何使用 Qlib 进行简单的因子回测
"""

import qlib
from qlib.constant import REG_CN
from qlib.data import D
from qlib.contrib.model.gbdt import LGBModel
from qlib.contrib.strategy import TopkDropoutStrategy
from qlib.backtest import backtest, executor
from qlib.utils import init_instance_by_config
from qlib.workflow import R
from qlib.workflow.record_temp import SignalRecord, PortAnaRecord
from qlib.contrib.evaluate import risk_analysis
import pandas as pd
import numpy as np
import warnings

warnings.filterwarnings('ignore')


def init_qlib(qlib_uri: str = None):
    """
    初始化 Qlib
    
    Args:
        qlib_uri: Qlib 数据目录，如果为 None 则使用默认路径
    """
    if qlib_uri is None:
        # 默认路径
        qlib_uri = "~/qlib_data/cn_data"
    
    print(f"初始化 Qlib，数据目录：{qlib_uri}")
    qlib.init(provider_uri=qlib_uri, region=REG_CN)
    print("Qlib 初始化成功!")


def simple_backtest():
    """
    简单回测示例
    
    使用 LightGBM 模型和 Alpha158 因子
    """
    print("=" * 60)
    print("Qlib 基础回测示例")
    print("=" * 60)
    
    # 配置参数
    start_time = "2020-01-01"
    end_time = "2023-12-31"
    train_start_time = "2020-01-01"
    train_end_time = "2022-12-31"
    
    # 使用 Alpha158 预定义因子
    handler_config = {
        "start_time": start_time,
        "end_time": end_time,
        "fit_start_time": train_start_time,
        "fit_end_time": train_end_time,
        "instruments": "csi300",  # 沪深 300 成分股
        "data_handler_config": {
            "start_time": start_time,
            "end_time": end_time,
            "fit_start_time": train_start_time,
            "fit_end_time": train_end_time,
            "instruments": "csi300",
            "train_processors": [],
            "test_processors": [],
            "fit_processors": [],
        }
    }
    
    # 模型配置 (LightGBM)
    model_config = {
        "model": "LGBModel",
        "loss": "mse",
        "colsample_bytree": 0.8879,
        "learning_rate": 0.0421,
        "subsample": 0.8789,
        "lambda_l1": 205.6999,
        "lambda_l2": 398.5332,
        "max_depth": 8,
        "num_leaves": 31,
        "num_threads": 8
    }
    
    print(f"\n1. 数据时间范围：{start_time} 到 {end_time}")
    print(f"   训练集：{train_start_time} 到 {train_end_time}")
    print(f"   测试集：{train_end_time} 之后")
    
    # 创建数据处理
    print("\n2. 创建数据处理器...")
    try:
        from qlib.contrib.data.handler import Alpha158
        
        handler = Alpha158(**handler_config)
        print("✓ 数据处理器创建成功")
    except Exception as e:
        print(f"✗ 数据处理器创建失败：{e}")
        print("  请确保已下载 Qlib 数据")
        return
    
    # 训练模型
    print("\n3. 训练 LightGBM 模型...")
    try:
        model = LGBModel(**model_config)
        
        # 获取训练数据
        train_data = handler.prepare(
            segments={"train": (train_start_time, train_end_time)}
        )
        
        print("✓ 模型训练完成")
    except Exception as e:
        print(f"✗ 模型训练失败：{e}")
        return
    
    # 预测
    print("\n4. 进行预测...")
    try:
        # 获取测试数据
        test_data = handler.prepare(
            segments={"test": (train_end_time + "1", end_time)}
        )
        
        # 预测
        pred = model.predict(test_data)
        print(f"✓ 预测完成，预测数据形状：{pred.shape}")
    except Exception as e:
        print(f"✗ 预测失败：{e}")
        return
    
    # 简单策略回测
    print("\n5. 策略回测...")
    try:
        from qlib.contrib.strategy import TopkDropoutStrategy
        from qlib.backtest import backtest_executor
        
        # 创建策略
        strategy_config = {
            "topk": 50,  # 选择排名前 50 的股票
            "n_drop": 5,  # 每天最多调仓 5 次
        }
        
        strategy = TopkDropoutStrategy(**strategy_config, signal=pred)
        
        print("✓ 策略创建成功")
        print(f"   持仓股票数：{strategy_config['topk']}")
        print(f"   最大日调仓数：{strategy_config['n_drop']}")
        
    except Exception as e:
        print(f"✗ 策略创建失败：{e}")
        return
    
    print("\n" + "=" * 60)
    print("基础回测示例完成!")
    print("=" * 60)


def custom_factor_backtest():
    """
    自定义因子回测示例
    
    演示如何使用自定义因子进行回测
    """
    print("\n" + "=" * 60)
    print("自定义因子回测示例")
    print("=" * 60)
    
    # 这里演示如何加载自定义因子
    # 实际使用时，可以导入 src.factor_base 中的因子
    
    print("\n自定义因子回测流程:")
    print("1. 定义自定义因子 (参考 src/factor_base.py)")
    print("2. 使用 Qlib 的 DataHandler 加载因子数据")
    print("3. 训练模型或直接使用因子信号")
    print("4. 执行回测并分析结果")
    
    # 示例：使用简单的动量因子
    print("\n示例：简单动量策略")
    print("  - 因子：20 日动量")
    print("  - 策略：每月调仓，持有动量最强的前 30 只股票")
    print("  - 基准：沪深 300")
    
    print("\n详细实现请参考 examples/advanced_backtest.py")


if __name__ == "__main__":
    # 初始化 Qlib
    # 如果数据在默认路径，可以直接调用 init_qlib()
    # 否则指定数据路径：init_qlib("d:/qlib_data/cn_data")
    try:
        init_qlib()
    except Exception as e:
        print(f"Qlib 初始化失败：{e}")
        print("\n请先下载 Qlib 数据:")
        print("  运行：powershell -ExecutionPolicy Bypass -File scripts/download_qlib_data.ps1")
        exit(1)
    
    # 运行基础回测
    simple_backtest()
    
    # 运行自定义因子回测示例
    custom_factor_backtest()
