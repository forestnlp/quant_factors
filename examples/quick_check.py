"""
快速检查 Alpha158 因子
"""

import qlib
from qlib.constant import REG_CN
from qlib.contrib.data.handler import Alpha158

# 使用正确的数据路径
DATA_PATH = "C:/Users/jay/qlib_data/cn_data"

print(f"初始化 Qlib，数据路径：{DATA_PATH}")
qlib.init(provider_uri=DATA_PATH, region=REG_CN)

print("\n加载 Alpha158 因子...")

# 创建一个简单的 handler 来查看因子
handler = Alpha158(
    start_time="2022-01-01",
    end_time="2022-01-10",
    fit_start_time="2022-01-01",
    fit_end_time="2022-01-10",
    instruments="csi300"
)

# 获取所有列名
cols = handler.get_cols()
print(f"\nAlpha158 因子总数：{len(cols)}")

print("\n=== 寻找振幅/波动相关因子 ===")
keywords = ['amp', 'vol', 'high', 'low', 'range', 'spread']
for col in cols:
    col_lower = col.lower()
    for kw in keywords:
        if kw in col_lower:
            print(f"  {col}")
            break

print("\n=== 前 20 个因子 ===")
for i, col in enumerate(cols[:20]):
    print(f"{i+1:3d}. {col}")
