# 量化因子开发系统

基于 **RD-Agent（自动化因子挖掘）+ Qlib（数据 / 因子 / 研究）+ Backtrader（策略回测）** 三者联合的量化因子开发框架，构建"数据 → 因子挖掘 → 回测验证"的完整闭环。

## 环境信息

- **Conda 环境**: `qlib_rdagent`（Python 3.10）
- **Qlib**: 0.9.7
- **RD-Agent**: 0.8.1.dev31
- **Backtrader**: 待安装
- **本地数据目录**: `C:/Users/jay/qlib_data/cn_data`（已本地化，含 calendars / features / instruments）

## 项目结构

```
quant_factors/
├── AGENTS.md                  # AI 协作方法论（Trae 自动加载）
├── examples/
│   └── amplitude_test.py      # 振幅突破因子 IC/IR 测试
├── .gitignore
└── README.md
```

## 快速开始

```powershell
conda activate qlib_rdagent
python examples/amplitude_test.py
```

## 技术分工

- **Qlib**: 数据加载、因子表达式计算、因子研究（IC/IR）
- **RD-Agent**: 自动化因子挖掘与迭代
- **Backtrader**: 策略回测与绩效分析

## 参考资料

- [Qlib 文档](https://qlib.readthedocs.io/)
- [RD-Agent 文档](https://rdagent.readthedocs.io/)
