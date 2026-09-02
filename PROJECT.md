# quant_factors — 项目目标、现状与路线

> **文档分工（仅两份）**：本文件讲「是什么 / 走到哪 / 学到什么」；`.trae/rules/rules.md` 讲「怎么思考 / 必须怎样」（IDE 自动注入）。

## 项目定位

- **名称**：quant_factors（因子 Loop Engineering 系统）
- **总目标**：本地大模型驱动、7×24 全自动闭环的因子挖掘系统——**取数 → 特征底座 → 自动挖掘 → Qlib 校验 → 负反馈迭代 → 私有因子库沉淀**。
- **当前阶段（第一阶段）目标**：**把数据搞到本地、搞准搞对，形成丰富特征**。特征底座不牢，后面的自动挖掘全是空中楼阁。
- **信念**：全程本地化私有化，数据、模型、因子资产无外泄（硬性约束见 rules.md R4-8）。

## 环境（单一 Python 环境）

**Conda `jaycode`** 承担全部计算与取数：`conda run -n jaycode python -m research.xxx ...`

- **聚宽通道**：jqcli 源码 vendored 于 `.tools/jqcli`（gitignore），以 `pip install -e .tools/jqcli` 装入 `jaycode` 环境（依赖 requests/websocket-client/python-dotenv，与 qlib 无冲突）。凭据只存 `.env` 的 `JQCLI_COOKIE`。
  两步重建：`git clone --depth 1 https://github.com/breakhearts/jqcli .tools/jqcli` → `conda run -n jaycode pip install -e .tools/jqcli`
- **本地大模型**：Qwen3.8-Flash（OpenAI 兼容，`.env` 的 `LLM_BASE_URL` / `LLM_API_KEY` / `LLM_MODEL`）。挖掘阶段接入，当前未启用。

## 根本问题一：聚宽研究环境能提供什么（能力地图）

价值 = 独有性 × 可获得性 − 风险。按证据强度分档，**只有"实测"档可建关键路径**（R4-9）。

**A. 实测确认可用**（一手证据）：

| 能力 | 实测边界 |
|---|---|
| `get_price` 日线 | 2005-01-04 起 5528 只（含 264 退市）；单次 33 万行/6.6s/27.5MB；`fq=None/post` 可用 |
| `get_call_auction` 竞价 | 单次 5000 行上限 → 按 2500 只分组 |
| `get_all_trade_days` | 5263 天已落盘（含未来占位日，落盘截断） |
| `get_all_securities` | 含上市/退市日期 → 幸存者偏差免疫 |
| download 通道 | 1.5MB/s，批量落盘主路（redis 中转实测慢 6 倍，弃） |

**B. 实测确认（2026-09-02 B 档探针，第二轮）**：`get_valuation`（日频全市场 5208 行，pe/pb/总市值/流通市值，单位亿元）、`get_money_flow`（主力/超大/大/中/小单净额与占比，无空值）、`get_mtss`（两融 9 列）、`get_extras('is_st')`、`get_billboard_list`（当日全市场 809 行）、`get_industry(date=)`（**行业 PIT 时变性实证**：中国石油 2010"采掘I"→2026"石油石化I"）、`get_concepts`/`get_concept_stocks`（399 概念）、`finance.STK_INCOME_STATEMENT`（**`pub_date`/`report_date` 字段实测存在**，经 `finance.run_query` 查询）。

**C. 确认不可用/不可信**：`factor` 复权因子（实测恒 1）、`get_split_ratio`（研究环境不存在该函数）、前复权（官方自认未来函数）、2005 年前行情、长历史分钟线、`jqdatasdk`（云端未装，只能用 `from jqdata import *`）。

**硬约束（架构边界）**：远端执行默认 120s 超时（`--execution-timeout` 显式放宽）；Cookie 会被平台回收（`JqAuthError` fail-fast，更新 `.env` 后重跑续传）；官方研究环境限速 500Kbps 且禁批量导出用途 → **取数一次性成批、克制低频**，不得当数据服务。

**决策**：历史行情主渠道全面转聚宽，起点 2005-01-04。旧 chenditc/AKShare 数据已删（备份下载地址见下文附录）。

## 根本问题二：需要什么特征、怎么存、怎么更新

一个字段成为特征须过三关：**① PIT 可考**（T 日可知，不看未来）**② 有增量信息**（本地字段换算不出）**③ 评估引擎能吃**。不过关的字段越多越毒——"越多越好"以此为闸门。

### 总体架构（四层，职责单向流动）

```
L1 raw 层    data/raw/jq/**          聚宽 CSV 分片，只追加，聚宽=唯一主源
L2 特征层    data/derived/features/  宽表 parquet（date×code×特征），幂等重建
L3 评估层    vectorbt + IC/IR + IS/OOS 切分，结果回喂因子库(duckdb/parquet)
L4 挖掘层    LLM 假设器（白名单 pandas 表达式）← 失败案例回喂
更新机制：fetch 重跑（断点续传）→ build 重跑（幂等）——无调度系统，一条命令即"定期更新"
```

**引擎定案（2026-09-02）**：评估/回测走 **vectorbt + 特征宽表**，不建 qlib bin——无二进制格式坑、pandas 全表达力（LLM 强项）、vectorbt 向量化原生支持 GPU（本机有显卡）、parquet 增量更新容易。qlib 降为可选导出格式，不进关键路径。老实现（qlib 表达式引擎等）在 git `42fc087`，仅参考不复用。

**数据源纪律**：聚宽证明缺什么，才允许为那一样东西开第二源（AKShare/Tushare/爬虫暂时一个都不加——多一源=多一份口径仲裁噩梦，cn_data 教训）。

### 特征清单（raw 层，按更新频率分层）

| 频率 | 数据集 | 关键字段 | 位置 | 状态 |
|---|---|---|---|---|
| 一次性 | 交易日历 | trade_days | `raw/jq/trading_calendar.csv` | ✅ 5263 天已落盘 |
| 一次性 | 标的清单 | code, start/end_date, 名称 | `raw/jq/securities.csv` | 待取（daily 云端在用，但未落盘） |
| 日度 | 日线 | 真实价 OHLCV+money、`high_limit`/`low_limit`/`paused` + 后复权 OHLC | `raw/jq/daily/` | ✅ **2020-01~2026-09（29 片 774.7 万行）**；2005~2019 待补 |
| 日度 | 估值 | pe/pb/market_cap/circulating_market_cap | `raw/jq/valuation/` | ✅ 2020~2026（109 片 770.5 万行） |
| 日度 | 资金流 | net_amount_main / net_pct_l 等 12 列 | `raw/jq/money_flow/` | ✅ 2020~2026（29 片 767.4 万行） |
| 日度 | 集合竞价 | 撮合价、竞价额、买卖一档量 | `raw/jq/auction/` | ✅ 2020~2026（162 片 768.2 万行） |
| 日度 | 两融 | fin_value/sec_value/买入额 9 列 | `raw/jq/mtss/` | ✅ 2020~2026（54 片 450.9 万行） |
| 事件 | 龙虎榜 | 席位买卖明细 | `raw/jq/billboard/` | ✅ 2020~2026（27 片 124.8 万行） |
| 日度 | ST 标记 | is_st 长表（只存 True） | `raw/jq/st/` | ✅ 2020~2026（25.4 万行） |
| 季度 | 概念成分 PIT | get_concept_stocks(399 概念) | `raw/jq/concept/` | ✅ 2020~2026（28 快照 92.7 万行；**成分确随时变**：半导体 2025-01=99 只 vs 2026-08=159 只） |
| 季度 | 行业 PIT | sw_l1/l2、jq_l1、zjw 代码+名称（季度末快照） | `raw/jq/industry/` | ✅ 2020~2026（28 快照 13 万行） |
| 事件 | 财务公告 | pub_date / report_date / end_date + 营收/净利/成本/EPS | `raw/jq/finance/` | ✅ 2020Q1~2026Q2（26 报告期 24.1 万行；含 report_type 预告；`run_query` 无 statDate，用 filter(end_date=)） |

**取数实测边界（写码必守）**：`get_valuation` 单次约 **1 万行上限**（静默截断！须逐日查询）；`get_money_flow` 无此限；**估值数据 T 日盘前不可得**（T 当天行全 NaN，T+1 生成）→ 增量更新的 end 应取 T-1，L2 对 NaN 行做 drop。

### 复权口径（实测决策，搞错则全量作废）

- `factor` 字段恒 1 → 无法自行换算复权，必须直接向聚宽取；
- 默认 `fq='pre'` 是未来函数（官方原话：使用未来复权因子，回测价格不正确）；
- **raw 存两套**：`fq=None` 真实价（涨跌停/停牌仅此口径有意义）+ `fq='post'` 后复权（历史不被未来分红改写）。**不存前复权。**

### 存储与更新（最简机制）

- **存储两层**：raw = CSV 分片，文件名含日期区间，天然幂等；derived = qlib bin（表达式引擎后端），挖掘阶段从 raw 重建，raw 永不由 derived 反向覆盖。
- **定时更新 = 重跑同一命令**：断点续跑保证幂等（已有片跳过、只补缺口），无需调度系统。每日增量即 `fetch daily --start <最后日期>`；Cookie 会过期决定了更新须有人在场或带告警，fail-fast + 续传即为此设计。

## 根本问题三：以后怎么自动挖掘因子（概要，挖掘阶段展开）

自动挖掘 = 闭环四件套，缺一即退化为随机试错：

```
假设器(LLM) → 编译器(qlib表达式) → 裁判(IC/IR + IS/OOS + 五层防御) → 记忆(因子库)
     ↑                                                          │
     └──────────── 失败案例与已有逻辑 回喂 Prompt ←──────────────┘
```

记忆层（去重防同质化、失败回喂防重复犯错）是 Loop 与试错的本质区别。四件的老实现存于 git `42fc087`（factor_miner / factor_eval / factor_lib / llm_client），届时按新特征底座重写。**当前不做**：raw 无字段可编译，提前建挖掘属投机工程。

**批判式吸收聚宽 jqfactor**：`analyze_factor` 与我们的评估链重叠；可吸收 `neutralize(how=[行业,size,beta])` 多风险中性化与 `max_loss` 有效率门槛；**须警惕**其默认 `weight_method='mktcap'` + 5 分位 + `periods=[1,5,10]` 组合易给乐观结论，且不提供样本内外切分——评估以自己链路为准。

## 附录：已删除数据的下载地址（备查，不再使用）

- **chenditc/investment_data qlib 全市场日线包**（曾用于 `data/cn_data`，846MB / 6166 只 / 2000-01~2026-08）：
  仓库 <https://github.com/chenditc/investment_data>，发布页 <https://github.com/chenditc/investment_data/releases>（取最新 release 的 `qlib_bin.tar.gz`，解压得 `calendars/features/instruments`）。弃用原因：不更新、与聚宽口径不可仲裁。
- **AKShare 申万行业映射/指数**（曾用于 `data/industry_map`）：`pip install akshare`，接口 `ak.sw_index_first_info()` / `ak.index_hist_sw()`。弃用原因：上游源不稳定（券商评测稳定性 2.41/5），行业改走聚宽 `get_industry(date=)` PIT。


## 引擎模块（`research/`，当前仅第一阶段所需）

| 模块 | 职责 |
|---|---|
| `config.py` | 路径统一读取：`raw_dir()` / `derived_dir()` / `jqcli_bin()` |
| `jq_channel.py` | 聚宽云端通道：jqcli 三段式（exec→download→rm）、分片、认证 fail-fast、交易日历 |
| `fetch.py` | 取数任务：`calendar` / `probe` / `daily` / `auction` / `valuation` / `money_flow` / `industry` / `concept` / `finance`，断点续跑 + 落盘覆盖核对 |
| `build.py` | **L2 特征层**：raw → `derived/features.parquet`（15 数值特征 + `fwd_ret_5` 标签，停牌 NaN 不填充）+ `industry/concept/finance.parquet` 维表；幂等可重建 |
| `check.py` | **数据体检门**：完整性/日历对齐/跨数据集主键与语义校验 + 交易规则对抗审计（涨跌停交易所口径、价格带、额量价、资金流守恒）；每次增量取数后必跑 |

评估（`factor_eval`）、因子库（`factor_lib`）、挖掘（`factor_miner`）、LLM 客户端（`llm_client`）等模块属于后续阶段，已在 git `42fc087` 保留，待特征底座成型后按需重写，不提前搬回。

```
# 第一阶段主命令（按顺序）
conda run -n jaycode python -m research.fetch calendar    # 最先：交易日历（已完成）
conda run -n jaycode python -m research.fetch probe       # 通道与体积探针
conda run -n jaycode python -m research.fetch daily       # 全市场日线（真实价+后复权，默认 2025 起）
conda run -n jaycode python -m research.fetch valuation   # 日频估值（逐日查询，15 天/片）
conda run -n jaycode python -m research.fetch money_flow  # 日频资金流
conda run -n jaycode python -m research.fetch industry --start 2025 --end 2026   # 行业 PIT 季快照
conda run -n jaycode python -m research.fetch concept --start 2025 --end 2026   # 概念成分 PIT 季快照
conda run -n jaycode python -m research.fetch finance --start 2024 --end 2026   # 财务公告（按报告期）
conda run -n jaycode python -m research.fetch auction --start 2010-01-01         # 竞价
conda run -n jaycode python -m research.build                                    # L2 宽表（raw 更新后重跑）
conda run -n jaycode python -m research.check                                    # 数据体检门
```

## 进度与下一步

**已完成**
- ✅ 通道打通与机制定型：云端执行 → `jq_out/` → download 本地 → 即删云端（含 `--execution-timeout` 显式放宽，默认仅 120s）
- ✅ 主渠道可行性定案 + 复权口径实测决策（见上）+ 历史深度定界（2005 起）
- ✅ 环境合并：jqcli 装入 conda `jaycode` 单环境，`.tools/venv-jqcli` 已删除
- ✅ 交易日历落盘并读回核对（5263 天，2005-01-04 ~ 2026-09-02）
- ✅ **日线小规模首战**：2025-01~2026-09 共 8 片 209.6 万行落盘；读回验证通过（行数≈理论值、涨跌停价=前收×1.1 精确、后复权比值随分红递增、双口径 NaN 一致）。实测单片（60 交易日×全市场）约 33MB/35s，比预估快一个量级
- ✅ 项目聚焦重构：只留取数引擎 + `docs/jq/`；旧数据/旧因子代码全部下线（git `42fc087` 可查）
- ✅ **多维取齐 2025~今**：估值（208 万行，修复 1 万行静默截断）、资金流（208 万行）、行业 PIT、概念 PIT（34.9 万行）、财务公告含 pub_date（8.3 万行）——全部过 `check.py` 体检门（含交易规则对抗审计：涨跌停交易所口径、价格带、额量价、资金流守恒，全绿）
- ✅ **L2 特征层建成**：`build.py` → `features.parquet` 209.6 万行 × 15 特征 + `fwd_ret_5` 标签；可用样本 196 万；茅台手工复算与宽表分毫不差
- ✅ **数据大扩张完成（2026-09-02）**：全部 10 个数据集补齐至 **2020-01~2026-09（6.7 年）**，raw 层共 **~4300 万行 / 约 4G**（日线 775 万、估值 771 万、资金流 767 万、竞价 768 万、两融 451 万、龙虎榜 125 万、ST 25 万、概念 93 万、行业 13 万、财务 24 万）。全区间过 `check.py` 体检门全绿（含时变涨跌停规则：创业板 2020-08-24 起 20%）；三个疑点均已定性（资金流缺"今天"=T+1 出数、茅台 10 差异日=除息日、标的数增长=市场扩容非跑漏）。**空间结论：2020~今全量 ~5G；补 2005~2019 约 12G——空间永不是约束**
- ✅ **生产化规划定调（详细设计待 L3 后）**：三层存储 raw→derived→`signals/`（每日选股信号，只追加）；更新=一条命令（fetch 增量→check 门→build→打分），无守护进程；选股口径统一"截至 T-1 完整数据选 T 日股"（估值/资金流 T+1 出数，天然 PIT 安全）；外部比对仅用 AKShare 月度锚点日 + 季度 --force 历史片 diff
- ✅ **分钟/tick 定位结论**：tick 历史聚宽本就没有（仅近期快照），永久搁置；分钟 K 历史有限且原始全量入库（~200GB/几十小时在线）与通道形态不匹配——**正确用法是将来"云端聚合、只取日频统计结果"**（尾盘动量/日内波动结构/量分布等），列为 L3 撞 IC 天花板后的预备役

**下一步（按序歼灭）**
1. **L3 评估层**：装 vectorbt，IC/RankIC/ICIR + 分层回测 + IS/OOS，跑通首批基线因子（动量/量能/估值/资金流各一）→ 验证：已知强信号（如放量负向）能被复现
2. 估值/资金流 **end 取 T-1** 的增量更新演练一次（定期更新机制实弹验证）
3. 竞价取数、2005~2024 历史补齐、行业/概念历史快照补齐（重跑命令即可，择机）
4. L4 挖掘层（LLM 假设器 + 因子库记忆）待 L3 稳定后开

## 已确立的研究结论

1. **量能 > 价格**：放量类是最强量价方向且为**负向**（放量→未来收益低），近 3 年震荡市成立（多轮交叉印证）。
2. **行业是分层不是信号层**：行业自身动量弱（RankICIR 0.1~0.2）；个股因子做行业相对化/中性化后信号更纯净（0.50→0.58）。
3. **集合竞价撮合价 = 开盘价**（复权后完全相等）→ 竞价的增量信息不在价格，而在竞价额、买卖五档失衡。
4. **单因子 IC 绝对值普遍 < 0.03**，须多因子合成；IC 数字不可当实盘预期。
5. LLM 可稳定产出 qlib 表达式因子，但须约束：不支持一元负号（写 `0 - X`）、不支持条件 Rank、不支持跨标的引用。

> 工程纪律与踩坑教训已固化到 `.trae/rules/rules.md` 第 5 节，本文件不再重复。

## 目录规划

`research/`（引擎工作区，入库）→ `src/`（正式区，入库）、`docs/`（文档，入库）、`data/`（gitignore）、`.tools/`（gitignore）。职责、流动与提升标准以 `.trae/rules/rules.md` R4 为唯一定义处。
