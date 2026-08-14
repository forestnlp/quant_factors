"""
检查 Qlib 数据是否正常
"""

import qlib
from qlib.constant import REG_CN
from qlib.data import D

# 初始化
qlib.init(provider_uri="C:/Users/jay/qlib_data/cn_data", region=REG_CN)

print("=" * 60)
print("Qlib 数据检查")
print("=" * 60)

# 1. 检查市场
print("\n=== 检查市场 ===")
try:
    markets = ["csi300", "csi500", "all"]
    for market in markets:
        try:
            instruments = D.instruments(market=market)
            print(f"✓ {market}: 有效")
        except Exception as e:
            print(f"✗ {market}: {e}")
except Exception as e:
    print(f"错误：{e}")

# 2. 检查股票列表
print("\n=== 检查股票列表 ===")
try:
    instruments = D.instruments(market="csi300")
    print(f"CSI300 类型：{type(instruments)}")
    print(f"CSI300 成分股数量：{len(instruments)}")
    
    # 正确获取股票列表
    if isinstance(instruments, str):
        # 如果是字符串，说明是市场名称
        print(f"市场名称：{instruments}")
        # 用 D.features 直接加载整个市场
        test_stocks = "csi300"
    else:
        # 如果是列表/集合
        stock_list = list(instruments) if not isinstance(instruments, list) else instruments
        print(f"前 10 只股票：{stock_list[:10]}")
        test_stocks = stock_list[:3]
    
except Exception as e:
    print(f"错误：{e}")
    import traceback
    traceback.print_exc()
    test_stocks = "csi300"

# 3. 检查数据时间范围
print("\n=== 检查数据时间范围 ===")
try:
    fields = ["$close", "$high", "$low", "$open", "$volume"]
    
    df = D.features(
        instruments=test_stocks,
        fields=fields,
        start_time="2022-01-01",
        end_time="2022-01-10",
        freq="day"
    )
    
    print(f"数据形状：{df.shape}")
    print(f"列名：{df.columns.tolist()}")
    if len(df) > 0:
        print(f"\n前 5 行数据:")
        print(df.head())
    else:
        print("⚠ 数据为空！检查时间范围或市场名称")
    
except Exception as e:
    print(f"错误：{e}")
    import traceback
    traceback.print_exc()

# 4. 检查自定义因子
print("\n=== 检查自定义因子表达式 ===")
try:
    # 测试简单振幅
    fields = [
        "$close",
        "$high",
        "$low",
        "Amp: ($high - $low) / $close",
    ]
    
    df = D.features(
        instruments=test_stocks,
        fields=fields,
        start_time="2022-01-01",
        end_time="2022-01-10",
        freq="day"
    )
    
    print(f"数据形状：{df.shape}")
    if len(df) > 0:
        print(df.head())
    else:
        print("⚠ 数据为空")
    
except Exception as e:
    print(f"错误：{e}")
    import traceback
    traceback.print_exc()

# 5. 尝试用 Alpha158 加载器
print("\n=== 尝试用 Alpha158 加载器 ===")
try:
    from qlib.contrib.data.handler import Alpha158
    
    handler = Alpha158(
        start_time="2022-01-01",
        end_time="2022-01-10",
        fit_start_time="2022-01-01",
        fit_end_time="2022-01-10",
        instruments="csi300"
    )
    
    df = handler.load()
    print(f"Alpha158 数据形状：{df.shape}")
    print(f"列数：{len(df.columns)}")
    if len(df) > 0:
        print(f"\n前 3 行:")
        print(df.head(3))
    
except Exception as e:
    print(f"错误：{e}")
    import traceback
    traceback.print_exc()

print("\n" + "=" * 60)
print("检查完成!")
print("=" * 60)
