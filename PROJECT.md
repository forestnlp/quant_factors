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

**B. 文档确认存在、未实测**（`docs/jq/api.md` 核对，用前须小样本探针）：`get_valuation`（日频 PE/PB/市值）、`get_money_flow`（主力/大小单资金流）、`get_mtss`（两融）、`get_billboard_list`（龙虎榜）、`get_extras('is_st')`、`get_split_ratio`（拆送转，复权的真正原料）、`get_fundamentals` + `finance.STK_*`（财务三表 + **pub_date 公告日**）、`get_industry(date=)`（行业 PIT）、`get_concept_stocks`/`get_index_stocks`（概念/指数 PIT）、`get_ticks`（股票 tick 仅近期）、`macro.run_query`（宏观）。

**C. 确认不可用/不可信**：`factor` 复权因子（实测恒 1）、前复权（官方自认未来函数）、2005 年前行情（2003 年请求返回 0 行，与官方文档一致）、长历史分钟线（待探针，预期有限）。

**硬约束（架构边界）**：远端执行默认 120s 超时（`--execution-timeout` 显式放宽）；Cookie 会被平台回收（`JqAuthError` fail-fast，更新 `.env` 后重跑续传）；官方研究环境限速 500Kbps 且禁批量导出用途 → **取数一次性成批、克制低频**，不得当数据服务。

**决策**：历史行情主渠道全面转聚宽，起点 2005-01-04。旧 chenditc/AKShare 数据已删（备份下载地址见下文附录）。

## 根本问题二：需要什么特征、怎么存、怎么更新

一个字段成为特征须过三关：**① PIT 可考**（T 日可知，不看未来）**② 有增量信息**（本地字段换算不出）**③ 评估引擎能吃**。不过关的字段越多越毒——"越多越好"以此为闸门。

### 特征清单（raw 层，按更新频率分层）

| 频率 | 数据集 | 关键字段 | 位置 | 状态 |
|---|---|---|---|---|
| 一次性 | 交易日历 | trade_days | `raw/jq/trading_calendar.csv` | ✅ 5263 天已落盘 |
| 一次性 | 标的清单 | code, start/end_date, 名称 | `raw/jq/securities.csv` | 待取（daily 云端在用，但未落盘） |
| 日度 | 日线 | 真实价 OHLCV+money、`high_limit`/`low_limit`/`paused` + 后复权 OHLC | `raw/jq/daily/` | **2025-01~2026-09 已落盘验证**（8 片 209.6 万行）；2005~2024 待补 |
| 日度 | 估值 | pe/pb/market_cap/circulating_market_cap | `raw/jq/valuation/` | 探针→待取 |
| 日度 | 资金流 | net_amount_main / net_pct_l 等 | `raw/jq/money_flow/` | 探针→待取 |
| 日度 | 集合竞价 | 撮合价、竞价额、买卖一档量 | `raw/jq/auction/` | 待取（2010 起） |
| 低频 | 两融/龙虎榜/拆送转/ST | get_mtss / get_billboard_list / get_split_ratio / get_extras | `raw/jq/…` | 探针→待取 |
| 季度 | 行业 PIT | code, in_date, out_date（区间表） | `raw/jq/industry/` | 待取（防前视核心） |
| 事件 | 财务公告日 | pub_date ≠ report_date | `raw/jq/finance/` | 待取（最高危未来函数） |

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
| `fetch.py` | 取数任务：`calendar` / `probe` / `daily` / `auction`，断点续跑 + 落盘覆盖核对 |

评估（`factor_eval`）、因子库（`factor_lib`）、挖掘（`factor_miner`）、LLM 客户端（`llm_client`）等模块属于后续阶段，已在 git `42fc087` 保留，待特征底座成型后按需重写，不提前搬回。

```
# 第一阶段主命令（按顺序）
conda run -n jaycode python -m research.fetch calendar    # 最先：交易日历（已完成）
conda run -n jaycode python -m research.fetch probe       # 通道与体积探针
conda run -n jaycode python -m research.fetch daily       # 全市场日线 2005 起（真实价+后复权）
conda run -n jaycode python -m research.fetch auction --start 2010-01-01
```

## 进度与下一步

**已完成**
- ✅ 通道打通与机制定型：云端执行 → `jq_out/` → download 本地 → 即删云端（含 `--execution-timeout` 显式放宽，默认仅 120s）
- ✅ 主渠道可行性定案 + 复权口径实测决策（见上）+ 历史深度定界（2005 起）
- ✅ 环境合并：jqcli 装入 conda `jaycode` 单环境，`.tools/venv-jqcli` 已删除
- ✅ 交易日历落盘并读回核对（5263 天，2005-01-04 ~ 2026-09-02）
- ✅ **日线小规模首战**：2025-01~2026-09 共 8 片 209.6 万行落盘；读回验证通过（行数≈理论值、涨跌停价=前收×1.1 精确、后复权比值随分红递增、双口径 NaN 一致）。实测单片（60 交易日×全市场）约 33MB/35s，比预估快一个量级
- ✅ 项目聚焦重构：只留 3 个取数文件 + `docs/jq/`；旧数据/旧因子代码全部下线（git `42fc087` 可查）

**下一步（集中优势兵力打歼灭战：只做取数）**
1. **全市场日线 88 片入库**（真实价+后复权双口径）→ 验证：每片打印行数/标的数/区间，收尾核对总覆盖 2005~今、行数 ≈ 标的日总数
2. **竞价取数**（2010 起，5000 行/次限制下按 2500 只×日分组）→ 验证：同上覆盖核对
3. **行业 PIT 区间表**（`get_industry(date=)` 按季取数折叠 in/out 区间）→ 验证：抽历史日期比对归属
4. **财务公告日表**（`pub_date` 对齐，防最高危未来函数）→ 验证：抽样比对公告日 ≥ 报告期
5. 取数全部落盘验证后，才进入特征加工（qlib bin）与挖掘阶段

## 已确立的研究结论

1. **量能 > 价格**：放量类是最强量价方向且为**负向**（放量→未来收益低），近 3 年震荡市成立（多轮交叉印证）。
2. **行业是分层不是信号层**：行业自身动量弱（RankICIR 0.1~0.2）；个股因子做行业相对化/中性化后信号更纯净（0.50→0.58）。
3. **集合竞价撮合价 = 开盘价**（复权后完全相等）→ 竞价的增量信息不在价格，而在竞价额、买卖五档失衡。
4. **单因子 IC 绝对值普遍 < 0.03**，须多因子合成；IC 数字不可当实盘预期。
5. LLM 可稳定产出 qlib 表达式因子，但须约束：不支持一元负号（写 `0 - X`）、不支持条件 Rank、不支持跨标的引用。

> 工程纪律与踩坑教训已固化到 `.trae/rules/rules.md` 第 5 节，本文件不再重复。

## 目录规划

`research/`（引擎工作区，入库）→ `src/`（正式区，入库）、`docs/`（文档，入库）、`data/`（gitignore）、`.tools/`（gitignore）。职责、流动与提升标准以 `.trae/rules/rules.md` R4 为唯一定义处。
