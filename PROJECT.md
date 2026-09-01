# quant_factors — 项目目标与定位

> **文档分工**：本文件只讲「是什么」——定位、架构、环境、数据（稳定事实）。「必须怎样」见 `.trae/rules/project-rules.md`，「怎么思考」见 `.trae/rules/methodology.md`，「走到哪/下一步」见 [ROADMAP.md](./ROADMAP.md)。

## 项目定位

- **名称**: quant_factors（因子 Loop Engineering 系统）
- **目标**: 搭建**本地大模型驱动、7×24 小时全自动闭环**的因子 Loop Engineering 系统，摆脱人工因子研发瓶颈，实现量化因子的**自动化挖掘 → Qlib 校验 → 负反馈迭代 → 私有因子库沉淀**。
- **信念**: 全程本地化私有化，数据、模型、因子资产无外泄（硬性约束以 project-rules 为准，本文不重复）。

## 环境（双 Python 线，严格隔离）

项目运行环境分**两条互不干扰的 Python 线**，禁止混装：

| 线 | 用途 | 运行方式 |
|---|---|---|
| **Conda `jaycode`** | 因子评估 / 挖掘 / qlib 数据层（主力环境） | `conda run -n jaycode python research/xxx.py ...` |
| **`.tools/venv-jqcli`** | 聚宽取数通道（jqcli CLI） | `./.tools/venv-jqcli/bin/jqcli research exec ...` |

**为什么隔离**：jqcli 依赖虽轻，但 qlib 的 numpy/pyarrow 版本树脆弱（曾花大力气解决冲突）；混装一旦版本冲突，修复成本极高。两条线各用各的解释器，互不影响。

- **Conda 环境**: `jaycode`（本机位于 `/home/chinapost/.conda/envs/jaycode`），已装 Qlib 0.9.7（pip 包名 `pyqlib`）、openai SDK、pandas/numpy。
- **聚宽通道（vendored 工具，gitignore）**：
  - `.tools/jqcli` — 第三方开源 jqcli 源码（vendored，封装聚宽研究环境的 Jupyter 协议远程执行）
  - `.tools/venv-jqcli` — 其专用 venv（独立解释器 + 轻依赖）
  - 凭据只存 `.env` 的 `JQCLI_COOKIE`（jqcli 经 `--env-file .env` 读取），不入代码/文档/git
  - **三步可重建**（整目录随时可删）：`git clone --depth 1 https://github.com/breakhearts/jqcli .tools/jqcli` → `python3 -m venv .tools/venv-jqcli` → `./.tools/venv-jqcli/bin/pip install -e .tools/jqcli`
- **本地大模型**: Qwen3.8-Flash（OpenAI 兼容接口，由 `.env` 的 `LLM_BASE_URL` / `LLM_API_KEY` / `LLM_MODEL` 指定）。
- **本地数据目录**: `data/cn_data`（由 `.env` 的 `QLIB_URI` 指定）；产物 `data/bt_export/`（代码自动创建）。

## 技术架构（三大牛鼻子）

1. **本地大模型适配 + Prompt 工程标准化**（解决挖掘质量）
   - `llm_client.py`：OpenAI 兼容调用封装，指向本地私有 API。
   - `factor_miner.py`：结构化 Prompt 约束，强制输出「因子假设 + Qlib 表达式 + 逻辑」，拒绝未来函数。
2. **Qlib 标准化 IC/IR 评估 + 五层过拟合防御**（解决因子真伪）
   - `factor_eval.py`：IC / RankIC / ICIR 评估 + 截面缩尾稳健标准化 + 行业中性化（无未来函数）。
   - 组合层回测采用 qlib `backtest`（TopkDropout 策略），不引入第二套回测栈。
3. **闭环调度 + 安全沙箱工程加固**（解决系统稳定）

### 引擎模块一览（`research/`）

| 模块 | 职责 |
|---|---|
| `config.py` | .env / QLIB_URI / LLM / 产物目录统一读取 |
| `data_fetcher.py` | 取数层：qlib 初始化、申万行业落盘与转 bin、`audit` 数据质量门 |
| `llm_client.py` | 本地大模型调用封装（OpenAI 兼容） |
| `factor_eval.py` | 因子评估：IC/RankIC/ICIR、截面缩尾、行业中性化 |
| `factor_lib.py` | 因子库（Loop 记忆）：SQLite 存全部生成因子/指标/轮次，去重与失败回喂 |
| `factor_miner.py` | Loop 主体：Prompt 生成 → 批量回测 → 双套指标落盘 |

> 当前进度与各 Phase Todo 见 [ROADMAP.md](./ROADMAP.md)。

## 数据体系（分层 + 主辅分离）

评估引擎的数据**必须驻留本地**；外部平台只做"取本地拿不到的独有数据"的增强件（见 project-rules 第 9 条）。

| 层级 | 数据 | 来源 | 落地 | 角色 |
|---|---|---|---|---|
| L1 行情 | 全市场日线（6135 只含退市，2000→至今，10 量价字段） | chenditc 投资数据包 | `data/cn_data` | **主**：评估引擎根基 |
| L1 行情 | 申万一级行业指数日线（31 个，1999→至今） | AKShare 申万系 → 转 qlib bin | `data/cn_data` + `instruments/sw_l1.txt` | 行业维度 |
| L2 结构 | 行业成分股映射（可再生产物，已落盘 `data/industry_map/`） | AKShare 快照（`data_fetcher.py industry` 重建） | `data/industry_map/` | 中性化（覆盖率 99.9%，剔除北交所） |
| L2 结构 | **行业 PIT**（按历史时点取归属，已验证可用） | 聚宽 `get_industry(security=list, date=)`（5528 只/次） | `data/industry_map/` | 消除"今天回看"前视 |
| L3 基本面 | 市值 / PB / 换手率（500 只一次）、**财务公告日** | 聚宽 `get_valuation` / `finance.STK_*`（`pub_date` 与 `report_date` 分离，实测存在） | `data/` | 中性化 + 财务 PIT |
| L3 基本面 | **涨跌停价** `high_limit/low_limit`、停牌 `paused`、ST `get_extras` | 聚宽 `get_price` | `data/` | 去泡沫化回测 |
| L3 基本面 | 聚宽**预置因子库 260 个**（财务/估值类为主，含 `momentum`、`market_cap`） | 聚宽 `jqfactor.get_all_factors` / `get_factor_values` | `data/` | 因子库种子、交叉验证 |
| L4 微观 | **集合竞价**（9:25 虚拟匹配价 `a1_p/b1_p` + 五档量，股票 2010 至今） | 聚宽 `get_call_auction`（**全市场 5126 只/次，硬上限 5000 行**） | `data/` | 竞价因子（此前误判"无免费源"） |
| L4 微观 | tick（2010 至今）、5min 线 | 聚宽 `get_ticks` / `get_price(frequency='5m')` | `data/` | 日内特征 |

> **聚宽 API 与 jqdatasdk 不同**：研究环境内核为 Python 3.6 老栈，`get_price` 多标的默认返回 Panel 需 `panel=False` 或走 dict；部分 jqfactor 函数需显式 `from jqfactor import ...`。完整官方文档已本地化于 `data/jq_docs/{api,factor}.md`（86 个签名级函数）。

**聚宽通道（机制已验证）**：`jqcli research exec --file <取数脚本>` 云端临时内核执行 → 结果 `to_csv` 写入云端 `jq_out/` → `jqcli research download` 拉回 `data/jq_stage/`（实测 1.2MB 文件秒级）。小结果走 stdout，大结果走 csv，redis 仅作备用高速通道。定位为**低频只读增强件**——平台风控/改版不影响已有资产，关键路径不依赖它。

**批判式吸收 jqfactor 因子分析范式**：其 `analyze_factor` 输出 IC/分层收益/换手率，与我们 `factor_eval` 重叠；**值得吸收**的是 `neutralize(how=[行业, size/beta/momentum...])` 多风险因子中性化与 `max_loss` 有效率门槛；**须警惕**的是它默认 `weight_method='mktcap'` 与 5 分位、`periods=[1,5,10]` 的组合易给乐观结论，且不提供样本内外切分——我们的五层过滤仍以自己的评估链为准。

**数据质量门**：`conda run -n jaycode python research/data_fetcher.py audit` 校验 bin 对齐、映射覆盖、数据新鲜度；FAIL 即中止评估。**任何写 qlib bin 的代码路径，收尾必须跑 audit 并抽样 `D.features` 读回比对**（bin 头部为 float32 起始索引、须补 NaN 到日历末尾，教训详见 ROADMAP「踩坑教训」）。

## 目录规划

采用「二区隔离 + 数据区 + 工具区」：`research/`(引擎工作区，入库) → `src/`(正式区，入库) 单线递进；`data/`(数据与产物，gitignore)、`.tools/`(第三方工具，gitignore)。

> 目录职责、流动规则与提升标准以 `.trae/rules/project-rules.md` 第 4 节为准（唯一定义处，本文不重复维护表格）。
