"""
playground: Qlib 数据获取学习脚本

目标：理解 Qlib 如何获取数据，验证"能否获取任意数据"。

核心结论（调研所得）：
1. 数据来源：本地目录 C:/Users/jay/qlib_data/cn_data（Qlib 官方 A 股日线数据）
2. 获取方式：D.features(instruments, fields, start_time, end_time)
   - 返回 MultiIndex DataFrame（instrument, datetime）
3. 可获取字段：$open/$high/$low/$close/$volume/$amount/$factor 等原始字段，
   以及任意 Qlib 表达式（如 Mean($close, 20)）
4. 能否获取任意数据：不能。只能获取本地 cn_data 中已有的数据。
   其他数据（分钟线、财务、其他市场）需额外下载或配置。
5. 关键坑（Windows）：循环内多次调用 D.features 会因 joblib 多进程卡死，
   应单次调用或避免循环。

验证标准：脚本能打印出指定股票、字段、时间范围的数据。
"""

import qlib
from qlib.constant import REG_CN

# 本地数据目录（数据已本地化，不依赖联网）
DATA_URI = "C:/Users/jay/qlib_data/cn_data"

# 初始化 Qlib
qlib.init(provider_uri=DATA_URI, region=REG_CN)
from qlib.data import D


def get_stock_list(market: str = "csi300") -> list:
    """获取股票列表（从 instruments 文件读取，最可靠）"""
    import os
    inst_file = f"{DATA_URI}/instruments/{market}.txt"
    instruments = []
    if os.path.exists(inst_file):
        with open(inst_file, "r") as f:
            for line in f:
                parts = line.strip().split("\t")
                if parts and parts[0]:
                    instruments.append(parts[0])
        instruments = list(dict.fromkeys(instruments))  # 去重
    return instruments


def get_features(instruments, fields, start_time, end_time):
    """获取特征数据"""
    return D.features(instruments, fields, start_time=start_time, end_time=end_time)


if __name__ == "__main__":
    print("=" * 60)
    print("Qlib 数据获取学习脚本")
    print("=" * 60)

    # 1. 获取股票列表
    stocks = get_stock_list("csi300")
    print(f"\n1. CSI300 股票数量：{len(stocks)}")
    print(f"   前 5 只：{stocks[:5]}")

    # 2. 获取单只股票的多字段数据
    print("\n2. 单只股票多字段数据：")
    fields = ["$open", "$high", "$low", "$close", "$volume", "$amount", "$factor"]
    df = get_features(["SH600000"], fields, "2023-01-01", "2023-01-10")
    print(f"   shape: {df.shape}")
    print(f"   字段: {df.columns.tolist()}")
    print(df.head(3))

    # 3. 获取多只股票数据
    print("\n3. 多只股票数据：")
    df_multi = get_features(stocks[:5], ["$close"], "2023-01-01", "2023-01-10")
    print(f"   shape: {df_multi.shape}")
    print(df_multi.head(5))

    # 4. 使用 Qlib 表达式（计算因子）
    print("\n4. Qlib 表达式（20日均线）：")
    df_expr = get_features(["SH600000"], ["Mean($close, 20)"], "2023-01-01", "2023-03-01")
    print(f"   shape: {df_expr.shape}")
    print(df_expr.head(3))

    print("\n" + "=" * 60)
    print("验证通过：Qlib 数据获取链路可用")
    print("=" * 60)
