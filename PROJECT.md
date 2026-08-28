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

## 目录递进（research 中间区）

代码遵循「`playground/`(实验) → `research/`(提炼验证) → `src/`(正式)」的升级路径：

- **`research/`** 为中间的**提炼/验证层**：从 playground 抽取、已去重整合但尚未最终定型，运行验证通过后整体提升到 `src/`。
- **当前 research 模块**：
  - `config.py` — .env / QLIB_URI 统一读取
  - `data_fetcher.py` — 数据采集层（qlib 全市场日线初始化 + 东财标的分钟K/日线采集）
  - `factor_eval.py` — 因子评估层（IC/RankIC/ICIR + 缩尾标准化）
  - `tests/test_research.py` — 冒烟测试

> 详细目录规则见 `.trae/rules/project-rules.md` 第 4 节。
