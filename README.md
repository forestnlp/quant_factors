# 量化因子开发与回测系统

基于 **Qlib** 和 **RD-Agent** 的量化因子开发框架

## 环境信息

- **Conda 环境**: `qlib_rdagent`
- **Python 版本**: 3.10
- **Qlib 版本**: 0.9.7
- **RD-Agent**: 已安装

## 快速开始

### 1. 激活环境

```powershell
conda activate qlib_rdagent
```

### 2. 下载数据

使用 Qlib 官方脚本下载：

```powershell
cd C:\Users\jay\qlib_data\qlib\scripts
python get_data.py qlib_data --target_dir C:/Users/jay/qlib_data/cn_data --region cn --interval 1d
```

或使用 Qlib 内置方法：

```python
from qlib.tests.data import GetData
GetData().qlib_data(target_dir="C:/Users/jay/qlib_data/cn_data", region="cn")
```

### 3. 配置环境变量

编辑 `.env` 文件，设置数据路径：

```
QLIB_URI=C:/Users/jay/qlib_data/cn_data
```

### 4. 运行示例

```powershell
# 基础回测
python examples/basic_backtest.py

# 查看因子开发示例
python src/factor_base.py

# 振幅因子测试
python examples/amplitude_test.py
```

## 项目结构

```
quant_factors/
├── src/                      # 源代码
│   └── factor_base.py       # 因子开发框架
├── examples/                 # 示例代码
│   ├── quick_check.py       # 快速检查数据
│   ├── amplitude_test.py    # 振幅因子测试
│   ├── basic_backtest.py    # 基础回测示例
│   └── rdagent_example.py   # RD-Agent 示例
├── .env                      # 环境变量
├── .gitignore
└── README.md
```

**数据目录**（外部，不纳入版本控制）:
- `C:/Users/jay/qlib_data/cn_data` - Qlib 数据
- `C:\Users\jay\qlib_data\qlib` - Qlib 源码

## 核心功能

### 因子开发

在 `src/factor_base.py` 中定义自定义因子：

```python
from src.factor_base import FactorBase

class MyFactor(FactorBase):
    def calculate(self, data):
        # data 包含 open, high, low, close, volume
        return data['close'].rolling(20).mean()
```

**内置因子**：
- 收益率因子
- 动量因子
- 波动率因子
- 成交量因子
- 高低区间因子

### 回测系统

- 支持 Alpha158 预定义因子
- LightGBM 模型训练
- TopK 策略回测
- 绩效分析

### RD-Agent 自动化

```powershell
# 需要配置 OpenAI API 密钥
rdagent fin_factor
```

## 配置说明

### 环境变量 (.env)

```
# Qlib 数据路径
QLIB_URI=~/qlib_data/cn_data

# OpenAI API (用于 RD-Agent)
OPENAI_API_KEY=your_key_here
```

### 使用清华镜像源

```powershell
pip config set global.index-url https://pypi.tuna.tsinghua.edu.cn/simple
```

## 参考资料

- [Qlib 文档](https://qlib.readthedocs.io/)
- [RD-Agent 文档](https://rdagent.readthedocs.io/)
