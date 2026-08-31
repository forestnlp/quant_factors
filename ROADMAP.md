# quant_factors — 目标与开发路线图

> 本文档记录项目的**总目标、当前进度（已完成）与后续任务（Todo）**。环境与定位见 [PROJECT.md](./PROJECT.md)，方法论见 `.trae/rules/methodology.md`，工程规则见 `.trae/rules/project-rules.md`。

## 一、项目总目标

构建「**数据 → 因子挖掘 → 回测验证**」的完整量化因子开发闭环：

1. **数据层**：本地化 Qlib A股日线数据，可更新、不依赖每次联网。
2. **因子层**：批量构造 / 筛选量价与基本面因子，用 IC / IR 等标准评估有效性。
3. **验证层**：分层单调性检验 + 组合回测（含交易成本），判断因子是否可用于选股与组合。
4. **策略层（后续）**：接入 RD-Agent 自动化挖掘 + Backtrader 策略回测。

---

## 二、当前进度（已完成）

### ✅ 阶段 1：环境与数据
- [x] Conda 环境 `jaycode` 安装 Qlib 0.9.7，解决 numpy/pyarrow 冲突。
- [x] `data/cn_data` 本地数据初始化为投资日更数据集（`chenditc/investment_data`，2026-08 前全市场约 5892 只股票）。
- [x] 数据初始化脚本 [init_qlib_data.py](./playground/init_qlib_data.py)（多镜像、断点续传、幂等）。

### ✅ 阶段 2：因子评估框架
- [x] 多因子 IC / IR 评估 pipeline：[factor_ic_ir_pipeline.py](./playground/factor_ic_ir_pipeline.py)。
- [x] 批量量价因子筛选：[factor_scan.py](./playground/factor_scan.py)，产出候选因子排序。

### ✅ 阶段 3：因子验证实验
- [x] TPD 两公式择时对比：[compare_tpd_factors.py](./playground/compare_tpd_factors.py)。
- [x] 选股分层检验 + 多头组合回测：[factor_portfolio_report.py](./playground/factor_portfolio_report.py)。

---

## 三、核心研究结论

1. **当前 A股环境（近3年震荡市）下，有效信号方向为「负向」**：放量 / 高波动的股票未来收益反而偏低（短期反转特征）。
2. **最强量价因子是「放量类」**：`turnover_ratio_5`（量能比）、`amt_trend` 表现优于 TPD、动量、波动率。分层单调性最清晰。
3. **TPD 类因子**：公式2 `(O+C)/2` 优于公式1 `(O+C+L+H)/4`，但两者本质同源、强度中上、非顶尖。
4. **交叉印证**：聚宽全市场因子库的负向因子（残差波动、成交量震荡、换手率相关）与本地结论一致，均指向「放量→下跌」。
5. **重要警示**：
   - 单因子 IC 绝对值普遍 <0.03，属微弱水平，需多因子合成。
   - 回测的年化数字基于乐观假设（全仓复利 + 低估摩擦 + 忽略涨跌停），**不可当实盘预期**。
   - 数据仅含量价字段，无法做行业 / 市值中性化；当前收益可能混入系统性效应。

---

## 四、Todo（待办任务）

### 🔴 优先级高
- [ ] **去泡沫化回测**：给组合回测加入「涨跌停买不进过滤 + 停牌处理 + 更高滑点」，得到接近实盘的收益，验证 turnover_ratio_5 是否仍有效。
- [ ] **参数稳健性测试**：测试不同持有周期（如 10 / 20 日）下因子是否依然稳定。

### 🟡 优先级中
- [ ] **Agent 自动挖掘日线量价因子**：基于 `research/factor_eval.scan_factors` 作为评估引擎，构建候选因子生成器（遗传式 / 随机搜索因子空间），迭代打分、自动挖掘新因子。
- [ ] **补充财务数据**：调研 tushare / akshare 等源为本地 qlib 数据补充财报字段，落地聚宽的「低成本强因子」（价值 / 现金流类，换手 1~2%）。
- [ ] **行业 / 市值中性化**：引入中性化后重新评估因子 IC，剥离系统性效应。

### 🟢 优先级低
- [ ] **多因子合成**：把第一梯队因子（放量反向 + 价值类）合成复合因子，提升 ICIR。
- [ ] **接入 RD-Agent**：自动化因子挖掘与迭代（若自研轻量 Agent 已够用可跳过）。
- [ ] **接入 Backtrader**：把选股结果落到策略回测与绩效分析。

---

## 五、目录速览

代码遵循「`playground/`(实验) → `research/`(提炼验证) → `src/`(正式)」递进路径。

| 文件 | 作用 |
|---|---|
| `research/config.py` | .env / QLIB_URI 统一配置读取 |
| `research/data_fetcher.py` | 数据采集层：qlib 全市场日线初始化 + 东财标的分钟/日线K |
| `research/factor_eval.py` | 因子评估层：IC/RankIC/ICIR + 截面缩尾标准化 |
| `research/strategies/tpd_redbar.py` | TPD「红柱放大」日内策略（扫描/成本/明细/绩效一条链） |
| `research/strategies/tpd_cross.py` | TPD「上穿/下穿」日内策略（扫描/样本外验证） |
| `research/tests/test_research.py` | research 冒烟测试 |
| `playground/init_qlib_data.py` | Qlib 数据初始化 / 更新（原实验记录） |
| `playground/factor_ic_ir_pipeline.py` | 多因子 IC/IR 评估（已提炼进 factor_eval） |
| `playground/factor_scan.py` | 批量量价因子筛选 |
| `playground/compare_tpd_factors.py` | TPD 两公式择时对比（日线全市场） |
| `playground/factor_portfolio_report.py` | 选股分层检验 + 组合回测报告 |
| `playground/tpd_backtest_513310.py` | 日线 TPD 趋势回测（513310） |
| `playground/intraday_orb_vwap.py` | ORB/VWAP 纯日内框架对比 |

> 说明：已被 `research/` 取代的抓取脚本与重复的 TPD 变体已删除（fetch_513310*.py、probe_513310_min.py、tpd_macd_bar*.py、tpd_intraday*.py），历史见 git 提交。

> 本文件为项目路线图，随开发进度持续更新。完成一项 Todo 后在对应复选框打勾。
