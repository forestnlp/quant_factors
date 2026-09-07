# HANDOFF.md — 会话交接板（冷启动先读我）

> 用途：任何新会话恢复任务的唯一入口。PROJECT.md 是现状全貌，本文件是"现在在哪、下一步打什么、怎么打"。
> 维护纪律：每场战役结束/路线改判/重大发现时更新本文件（与 PROJECT.md 同步），随代码一起提交。
> 最后更新：2026-09-07（commit 1a6e778）

## 一、我们在做什么（30 秒版）

双产品共底座：**产品一·因子机器**（LLM 全自动挖掘→验证→维护私有因子库）；**产品二·荐股机器**（中远期，基于因子库每日荐股）。硬约束：**只能买股票+持现金，无融券**；全程本地私有、零外泄。研究纪律见 `.trae/rules/rules.md`，验证协议 v2（滚动 WFO，旧 OOS 已消费作废）见 PROJECT.md。

## 二、当前阵地（已验证的事实，可直接信任）

- **数据**：12 数据集 2020-01~2026-09-07（财务三表 2019Q1 起）；宽表 `data/derived/features.parquet` 776 万行 × 38 特征 + 标签，check 体检门全绿（含九节财务体检：BS 恒等式 24.28 万行仅 10 违例）
- **官方答案库**：`data/raw/jq/alpha_ref/` 33 片全历史 alpha101；`derived/alpha_board.csv` 87 因子同口径榜单（auc 入全场 Top12；官方头部=正向结构类，与自家负向量能类互补）
- **裁判体系**：eval.py（IC/ICIR/分层，秒级）+ backtest.py（vectorbt 组合层，自证与手算误差 2e-16）；对答案获官方盖章（alpha_002/006 Pearson 0.999+）
- **更新机制**：`python -m research.update --deep` 一键补到最新（断点续跑=更新，实战验证 4 次）；通道独占锁防并发
- **弹药库**：见 FACTORS.md——候选三强（v_amt_5_20 / auc_money_share / vlm_turnover）+ 财务 9 特征刚进场（未测）

## 三、下一场战役（按序，别跳）

1. **财务特征首测**（原料刚进场，趁热）：`conda run -n jaycode python -m research.eval fin_roe_ttm fin_gross fin_rev_yoy fin_cash_quality fin_debt` 看量价世界之外的第一份 IC 成绩单；成长/质量因子在 A 股 2020~2026 有没有肉，一枪 know
2. **现货约束下三强弹药 WFO 重验收**：滚动 walk-forward + 绝对收益/回撤口径（基准沪深300/中证500），产出第一个可执行的"产品"（band 多头形态，参考 `backtest.py run_band`）
3. **人肉挖掘彩排**：按"假设→编译→裁判→记账(FACTORS.md)"走 3~5 轮（财务特征给了新假设空间），沉淀 Prompt/拒收规则；L4 自动化前必过 PROJECT.md 七形态对策表
4. L4 实装（LangGraph 首选，见 PROJECT.md 选型结论）；择机：仓位择时、2005~2019 回填、signals/ 层

## 四、环境与坑（新会话必读）

- 环境：conda `jaycode` 单环境（jqcli 已 `pip install -e` 集成）；jqcli 在 `.tools/jqcli`；**plotly 必须 <6**（vectorbt 依赖）
- 取数通道：`research/jq_channel.py`（exec→download→rm 三段式，O_EXCL 独占锁；**同一时刻只允许一个进程走通道**）；Cookie 会过期——`jqcli research exec -c "print(1)" --yes` 探针，失败则让用户重登聚宽更新 `.env` 的 `JQCLI_COOKIE`
- 云端陷阱：jqcli exec 报错 returncode 仍为 0（已在 jq_channel 抛修）；估值/资金流 T+1 出数；`get_valuation` 1 万行静默截断
- 财务口径：聚宽利润表/现金流=**年度内累计值**（TTM 换算在 build.py `_fin_prep`）；**期间平移方向是未来函数高发区**（首版写反被茅台对答案当场抓获，教训在 PROJECT.md 下一步#2）；特征生效日=三表 pub_date 取晚
- 验证纪律：落盘必读回核对范围；OOS 已作废，一切验收用滚动 WFO；重大发现即时归档（rules 第 5 节第 6 条）

## 五、常用命令速查

```bash
conda run -n jaycode python -m research.update --deep   # 每日更新（幂等，重跑=续传）
conda run -n jaycode python -m research.check           # 体检门（含九节财务）
conda run -n jaycode python -m research.build           # 重建 L2 宽表
conda run -n jaycode python -m research.eval <因子...>  # IC 裁判
conda run -n jaycode python -m research.backtest <因子> -k 100 --rebal 10  # 组合裁判
conda run -n jaycode python -m research.fetch <task> --start ... --end ... # 取数（断点续跑）
```
