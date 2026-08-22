# quant_factors — 项目目标与定位

本文档描述项目的**目标、技术分工与环境**。开发过程中的**方法论**见 `.trae/rules/methodology.md`，**硬性工程规则**见 `.trae/rules/project-rules.md`。

## 项目定位

- **名称**: quant_factors（量化因子开发系统）
- **目标**: **RD-Agent（自动化因子挖掘）+ Qlib（数据 / 因子 / 研究）+ Backtrader（策略回测）三者联合应用**，构建"数据 → 因子挖掘 → 回测验证"的完整闭环。
- **核心原则**: 下载的数据**最好保存在本地**，不依赖每次联网，方案要服从本地数据与环境的真实情况。

## 环境

- **Conda 环境**: `jaycode`（本机位于 `/home/chinapost/.conda/envs/jaycode`）。
- **已装**: Qlib 0.9.7（pip 包名 `pyqlib`）、Backtrader。
- **待定**: RD-Agent（如需要再安装）。
- **本地数据目录**: `data/cn_data`（相对项目根，实际由 `.env` 中的 `QLIB_URI` 指定）。

## 技术分工（抓主要矛盾）

- **Qlib**: 负责数据加载、因子表达式计算、因子研究（IC/IR）。
- **RD-Agent**: 负责自动化因子挖掘与迭代。
- **Backtrader**: 负责策略回测与绩效分析。
- 三者以"Qlib 数据 → 因子 → 回测"为主线串联，避免职责混乱。
