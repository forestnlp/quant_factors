"""
振幅突破因子测试 - 最终版

直接用 Qlib 表达式引擎加载数据并计算 IC
"""

import qlib
from qlib.constant import REG_CN
from qlib.data import D
import pandas as pd
import numpy as np

# 初始化
qlib.init(provider_uri="C:/Users/jay/qlib_data/cn_data", region=REG_CN)

print("=" * 60)
print("振幅突破因子测试")
print("=" * 60)

# ============================================
# 1. 定义因子表达式
# ============================================

print("\n=== 因子表达式 ===")

# 直接用 Qlib 表达式加载数据
fields = [
    "$close",                           # 收盘价
    "$high",                            # 最高价
    "$low",                             # 最低价
    "$open",                            # 开盘价
    "$volume",                          # 成交量
    
    # 自定义振幅因子
    "SHAmp: ($high - $low) / $close",                    # 当日振幅
    "SHAmpMean20: Mean(($high - $low) / $close, 20)",   # 20 日平均振幅
    "SHAmpRatio: (($high - $low) / $close) / Mean(($high - $low) / $close, 20)",  # 振幅比率
    
    # 收益率
    "SHRet1D: Ref($close, 1) / $close - 1",  # 1 日收益率
]

print("加载的字段:")
for f in fields:
    print(f"  {f}")

# ============================================
# 2. 加载数据
# ============================================

print("\n=== 加载数据 ===")

start_time = "2022-01-01"
end_time = "2023-12-31"

# 获取 csi300 股票列表（直接读取成分股文件，最可靠）
import os
inst_file = "C:/Users/jay/qlib_data/cn_data/instruments/csi300.txt"
instruments = []
if os.path.exists(inst_file):
    with open(inst_file, "r") as f:
        for line in f:
            parts = line.strip().split("\t")
            if len(parts) >= 1 and parts[0]:
                instruments.append(parts[0])
    # 去重
    instruments = list(dict.fromkeys(instruments))
print(f"CSI300 股票数量：{len(instruments)}")
print(f"前 5 只：{instruments[:5]}")

df = D.features(
    instruments=instruments,
    fields=fields,
    start_time=start_time,
    end_time=end_time,
    freq="day"
)

print(f"数据形状：{df.shape}")
print(f"列名：{df.columns.tolist()}")

# ============================================
# 3. 计算 IC
# ============================================

print("\n=== IC 计算 ===")

# 重命名列以便处理
df = df.copy()
df.columns = ['close', 'high', 'low', 'open', 'volume', 
              'amplitude', 'amp_mean_20', 'amp_ratio', 'ret_1d']

# 按日期计算 IC
dates = df.index.get_level_values("datetime").unique()
daily_ics = []

print("计算每日 IC...")
count = 0
for date in dates:
    try:
        # 获取当日数据
        day_mask = df.index.get_level_values("datetime") == date
        day_data = df[day_mask]
        
        # 计算 IC
        factor = day_data['amp_ratio']
        ret = day_data['ret_1d']
        
        # 去除 NaN
        mask = factor.notna() & ret.notna()
        if mask.sum() > 50:
            ic = factor[mask].corr(ret[mask], method="spearman")
            if not np.isnan(ic):
                daily_ics.append({"date": date, "ic": ic})
        
        count += 1
        if count % 50 == 0:
            print(f"  已计算 {count} 天...")
    except Exception as e:
        continue

ic_df = pd.DataFrame(daily_ics)

# ============================================
# 4. IC/IR 统计
# ============================================

print("\n" + "=" * 60)
print("IC/IR 统计结果")
print("=" * 60)

if len(ic_df) > 0:
    ic = ic_df['ic']
    
    print(f"\n有效天数：{len(ic_df)}")
    print(f"\nIC 统计:")
    print(f"  IC 均值：{ic.mean():.4f}")
    print(f"  IC 中位数：{ic.median():.4f}")
    print(f"  IC 标准差：{ic.std():.4f}")
    print(f"  IC 最小值：{ic.min():.4f}")
    print(f"  IC 最大值：{ic.max():.4f}")
    
    print(f"\nIC IR (信息比率): {ic.mean()/ic.std():.4f}")
    print(f"IC > 0 比例：{(ic > 0).mean()*100:.1f}%")
    print(f"|IC| > 0.02 比例：{(ic.abs() > 0.02).mean()*100:.1f}%")
    print(f"|IC| > 0.05 比例：{(ic.abs() > 0.05).mean()*100:.1f}%")
    
    # IC 趋势
    print(f"\nIC 时间趋势:")
    ic_df['month'] = ic_df['date'].dt.to_period('M')
    monthly_ic = ic_df.groupby('month')['ic'].mean()
    print(monthly_ic.head(6))
else:
    print("无法计算 IC，数据可能有问题")

# ============================================
# 5. 因子描述统计
# ============================================

print("\n" + "=" * 60)
print("因子描述统计")
print("=" * 60)

print(f"\n振幅 (amplitude):")
print(f"  均值：{df['amplitude'].mean():.4f}")
print(f"  中位数：{df['amplitude'].median():.4f}")
print(f"  标准差：{df['amplitude'].std():.4f}")

print(f"\n振幅比率 (amp_ratio):")
print(f"  均值：{df['amp_ratio'].mean():.4f}")
print(f"  中位数：{df['amp_ratio'].median():.4f}")
print(f"  标准差：{df['amp_ratio'].std():.4f}")
print(f"  > 2.0 的比例：{(df['amp_ratio'] > 2.0).mean()*100:.1f}%")
print(f"  > 3.0 的比例：{(df['amp_ratio'] > 3.0).mean()*100:.1f}%")

print("\n" + "=" * 60)
print("测试完成!")
print("=" * 60)
