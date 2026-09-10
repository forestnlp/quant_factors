# HANDOFF.md — 会话交接板（冷启动先读我）

> 用途：任何新会话恢复任务的唯一入口。PROJECT.md 是现状全貌，本文件是"现在在哪、下一步打什么、怎么打"。
> 维护纪律：每场战役结束/路线改判/重大发现时更新本文件（与 PROJECT.md 同步），随代码一起提交。
> 最后更新：2026-09-10 午（三步歼灭战+家族代表制全部执行完毕：WFO 清洗 43/44 过、dig 收紧 v2 复产、famcorr 出表、9 支家族重复退役——**现役=3 product + 36 candidate（34 过线代表+2 新挖）**；**下一步=合成战役三战**（池=代表+产品，族折减权重用 famcorr.json；先预注册再打），详见 PROJECT.md 结论28/29）

## 一、我们在做什么（30 秒版）

双产品共底座：**产品一·因子机器**（LLM 全自动挖掘→验证→维护私有因子库）；**产品二·荐股机器**（中远期，基于因子库每日荐股）。硬约束：**只能买股票+持现金，无融券**；全程本地私有、零外泄。研究纪律见 `.trae/rules/rules.md`，验证协议 v2（滚动 WFO，旧 OOS 已消费作废）见 PROJECT.md。

## 二、当前阵地（已验证的事实，可直接信任）

- **数据**：12 数据集 2020-01~2026-09-07（财务三表 2019Q1 起）；宽表 `data/derived/features.parquet` 776 万行 × 38 特征 + 标签，check 体检门全绿（含九节财务体检：BS 恒等式 24.28 万行仅 10 违例）
- **官方答案库**：`data/raw/jq/alpha_ref/` 33 片全历史 alpha101；`derived/alpha_board.csv` 87 因子同口径榜单（auc 入全场 Top12；官方头部=正向结构类，与自家负向量能类互补）
- **裁判体系**：eval.py（IC/ICIR/分层，秒级）+ backtest.py（vectorbt 组合层，自证与手算误差 2e-16）；对答案获官方盖章（alpha_002/006 Pearson 0.999+）
- **更新机制**：`python -m research.update --deep` 一键补到最新（断点续跑=更新，实战验证 4 次）；通道独占锁防并发
- **弹药库**：**首个 product = `a_rev_x_lowvol`**（反转×低波交互，WFO 6/7 坐实；**持仓形态定档 Top-10、10 日调仓**，含费全区间 +13.8%/0.66）；候选 a_quiet_two/v_amt/auc/vlm/fin_cash_quality/bb_yest；教训档 a_cold_horse（IC 最强≠组合）。机器账本 `factorlib list`，人读 FACTORS.md
- **彩排规范**：`research/PROPOSE.md`（作业五步流程+7 条拒收规则+7 条有效模式+L4 Prompt 骨架）——三轮彩排沉淀，LLM 假设器的母本
- **L4 工具契约层（2026-09-08 建成，全流程串通实测）**：`alpha.py` 白名单 DSL 编译器（LLM 产出唯一入口，注入攻击全拦）→ `eval --json`（裁判机器可读，自动加载 alpha 产物）→ `factorlib.py`（机器账本 `derived/factorlib.json`：状态机 candidate→product→retired/rejected + 去重 `exprs`）→ `sentinel.py`（在库因子近 250 日复算，翻转判死/衰减判伤，首跑 6 因子全绿）。契约=命令行参数入、JSON 出、错误非零退出，任何壳（dsh/LangGraph）可按同一契约指挥

## 三、下一场战役（按序，别跳）

**收益目标账（2026-09-08 与用户对齐）**：目标费后年化 ≥50%。已实测的暴露地图：现货多头域（无融券）最优 band +8.8%/Sharpe 0.46、等权基准 +10%/0.56——**现货多头域距 50% 很远且无 alpha**；钱在负向端（结论11/12）；仓位择时路线已经预注册判决并由用户终裁关闭（结论20，产品永远满仓），剩余合法收割=**事件减法 + 未来合规做空工具**。路径：①信号做深（弹药+WFO+L4 挖掘，**主战场**）②结构做对（减法/未来合规做空工具）③可加杠杆的前提是 Sharpe 高（50%≈Sharpe2+×2x 杠杆，另一条腿是期货/两融授信，属资金面）。

1. ~~精选度战役~~ ✅ **2026-09-08 判决（结论19）**：预注册 k∈{5,10,20} 仅按 IS 选优 → **k=10 当选**（IS 0.79），补 WFO 严考 6/7 过、最佳单年贡献 27% → **产品二形态定档：Top-10、每 10 交易日调仓**（全区间 +13.8%/0.66）。集中度代价如实记：2026 段 -9.4%、费用 70.7%（择时层已独立成役并终裁，见下）
2. ~~仓位择时战役~~ ⚠️ **2026-09-08 判决 FAIL（结论20，但含重要未兑现价值）**：IS 当选 MA20+半仓（IS 0.87>0.79），全区间年化 +13.2% < 基线 +13.8% → 预注册"年化必须同升"一票否决。**防守端实际大胜**：回撤 -34.2%→-22.1%、Sharpe 0.66→0.79、Calmar 0.40→0.60、2026 段 -9.4%→-4.2%。**标尺错误自曝**：牛市里防守层结构上不可能年化更高，线定死了必输。**用户终裁（2026-09-08）：彻底判死、不再回头——择时路线关闭，Top-K 产品永远满仓，不设降仓开关**（timing.py 保留作历史工具，勿再投入）
3. ~~L4 换假设器~~ ✅ **2026-09-08 上线实弹（结论21）**：探枪全过（JSON mode + function-calling 原生可用）→ `dig.py` 回路建成，2 轮试猎 **1 过 1 拒零人工**：首猎 `a_retail_chase_quiet`（散户小单追逐×低换手，IS ICIR **0.907 建库最高**、IS 年化 +8.3%/0.52）入 candidate。**09-09 补**：误杀重提——`a_quality_quiet`（财务×量价异族，IS 0.53）过线入 candidate，`a_low_vol_quiet` 被真去重门拒（换皮）。**待办：批量夜跑需用户批准（建议 --rounds 20 --patience 5）**；新候选升 product 一律走人工 WFO 预注册
4. ~~轮换扩池~~ ❌ **2026-09-09 判死（结论22）**：三族池轮换 0.55 < 池内最优 0.65，6 次换枪错 3 次——**问题在机制不在池**（按上年 Sharpe 选枪=追噪声）。增益改走"**多因子等权合成**"（下条 P0）
5. ~~P0 合成战役~~ ❌ **2026-09-09 判决 FAIL（结论24）**：预注册线 IS Sharpe>0.632 且 WFO 正年≥6/7 → 实测 **IS 0.611 不过线**（WFO 6/7 达标不作抵赖）。合成枪全区间 +11.5%/0.63 < 现役 +12.6%/0.65。**与轮换同根结论：池子同质化未解决前，组合花样零增值**——增益只能来自真正不同的信号源（P1）。synth.py 留作工具，a_synth_f4 不荐股。同日两枪转正 **product**：a_retail_chase_quiet、a_quality_quiet（用户批准）；本批 6 新候选 WFO 全员过线（4/7~6/7，全区间 0.47~0.53）仍为 candidate
6. ~~P1 分钟→日频特征~~ ❌ **2026-09-09 试点终判 FAIL（结论26，两周期全灭+OOS 已消费）**：管道全通（fetch min_agg 云端聚合 51s/日 + build_min 七特征），5 抽月 93 片取数完成。5 日标签：唯一 IS 过线 m_pull30 → OOS 2026-06 ICIR -0.060 反号 FAIL；1 日标签公正复检亦全灭（m_pull30 差 0.06 压线）。**风向标（m_lead30）证伪、开盘价格特征无信号、抢跑惩罚仅 2020-22 稳（2023 翻转）**。留下资产：min_agg 原料底座+全链路管道（日内策略/全期回填随时可启用）。**教训：验证前先核对标签周期与假设周期匹配**（勿再犯）。分钟域若再战=日内策略形态（持仓<1日），需新预注册，暂不排期
7. **signals/ 层已建成（2026-09-09 晚）**：`python -m research.signals` 输出当日应持 Top-10/买卖动作（选股直调 backtest.topk_weights 同一实现，08-25 独立复算逐票一致；持仓=数据纯函数无状态文件）。**顺手堵住系统性缺口**：alpha 产物是编译时快照、update 重建宽表后不自动跟新（实查 a_rev_x_lowvol 停 09-07）→ signals 内置 `_refresh_alpha`（产物截止<宽表截止→按账本表达式自动重编译）。执行口径诚实声明：回测按信号日收盘成交，实盘次日下单有约 1 日漂移，以实盘实测为准。执行节奏：数据截止日恰为调仓日（全局第 10n 交易日）才换仓，其余日维持
8. P3 新闻/CCTV 情绪因子：**通道实测不通**（09-09 云端探针：研究环境无 get_cctv_news/get_news，属 JQData 商业版）；传导链最长，最低优先级
9. ~~待用户确认转正~~ ✅ 09-09 用户批准，a_retail_chase_quiet / a_quality_quiet 已转 product（账本+FACTORS 同步）
10. **⚠️ 09-09 批量挖掘诚实警示（合成战役前必读）**：首批 17 轮过线 6 个，但**表达式全部含 mf_net_pct_main（主力净流入）**——同一味原料的家族簇，IS 多重检验风险高；去重门（秩相关>0.9）挡住了换皮但挡不住"同原料不同配方"。**合成前必须先给 6 个新候选跑 WFO，且合成权重按家族簇折减**（同簇视为一支枪）

## 四、术语人话对照（用户读文档遇到生词查这里；汇报一律用大白话）

| 黑话 | 人话 |
|---|---|
| 对抗审计 | 不信任数据源，拿外部硬规矩（涨停价=前收×1.1、资产=负债+权益等）反过来考数据，查"对不对"；普通检查只查"齐不齐" |
| 体检门 / check | 每次取完数必跑的一套自动检查，全绿才算这批数据可用 |
| 断点续跑 / 幂等 | 中断后重跑同一条命令，已完成的跳过、只补没做的，跑几遍结果一样 |
| PIT（point-in-time） | 只用"当天真实知道的信息"算指标，不许偷看未来（如财报按公告日生效，不按报告期） |
| 未来函数 | 算今天的信号却用到了今天之后才知道的数据，回测虚假好看、实盘必亏 |
| IS / OOS / WFO | 练习题（拿来调参）/ 考卷（只在验收时看）/ 滚动考卷（每轮验收都用没做过决定的新时段） |
| IC / RankIC / ICIR | 因子值与未来收益的相关性 / 排名相关性 / 稳定度（均值÷波动，>0.3 算不错） |
| 分层 / 十分位 | 每天按因子值把股票分 10 组看收益差，验证因子是不是单调有用 |
| band / 选股带 | 不买因子值最极端的头 10%（微票陷阱），只买排名 10%~50% 区间 |
| 换手 / 费后 | 调仓频率带来的交易成本；"费后"=扣完佣金印花税滑点还剩的收益 |
| Sharpe / 回撤 | 每承担一份波动换来的收益 / 从最高点跌到最低点的最大跌幅 |
| 歼灭战 / 战役 / 判决 | 一次只聚焦一个目标做完验证；一个研究专题；用事前定的及格线做非黑即白的结论（不达标就关闭路线） |
| 弹药 / 因子库 | 验证过有信号的候选因子 / 归档管理它们的台账（FACTORS.md） |

## 五、环境与坑（新会话必读）

- 环境：conda `jaycode` 单环境（jqcli 已 `pip install -e` 集成）；jqcli 在 `.tools/jqcli`；**plotly 必须 <6**（vectorbt 依赖）
- 取数通道：`research/jq_channel.py`（exec→download→rm 三段式，O_EXCL 独占锁；**同一时刻只允许一个进程走通道**）；Cookie 会过期——`jqcli research exec -c "print(1)" --yes` 探针，失败则让用户重登聚宽更新 `.env` 的 `JQCLI_COOKIE`
- 云端陷阱：jqcli exec 报错 returncode 仍为 0（已在 jq_channel 抛修）；估值/资金流 T+1 出数；`get_valuation` 1 万行静默截断；**量价/龙虎榜晚 8 点后才能抓 T 日（盘中=半天快照毁数据，2026-09-07 事故，update.py CLOSE_HOUR 已机制化，rules 第 7 条）**
- 财务口径：聚宽利润表/现金流=**年度内累计值**（TTM 换算在 build.py `_fin_prep`）；**期间平移方向是未来函数高发区**（首版写反被茅台对答案当场抓获，教训在 PROJECT.md 下一步#2）；特征生效日=三表 pub_date 取晚
- 验证纪律：落盘必读回核对范围；OOS 已作废，一切验收用滚动 WFO；重大发现即时归档（rules 第 5 节第 6 条）
- **dig 批 rc=139（09-09/09-10 两次）**：开批 1-2 秒零输出即崩，疑凶=conda run 包装层（监工已改直连 env python + PYTHONFAULTHANDLER 留栈）；**杀监工须连退避 sleep 子进程一起清**（孤儿继承 flock fd → 新监工被单实例锁静默挡下，09-10 已加 EXIT trap 根治）

## 六、常用命令速查

```bash
conda run -n jaycode python -m research.update --deep   # 每日更新（幂等，重跑=续传）
conda run -n jaycode python -m research.check           # 体检门（含九节财务）
conda run -n jaycode python -m research.build           # 重建 L2 宽表
conda run -n jaycode python -m research.eval <因子...>  # IC 裁判（--json 机器可读）
conda run -n jaycode python -m research.backtest <因子> -k 100 --rebal 10  # 组合裁判
conda run -n jaycode python -m research.fetch <task> --start ... --end ... # 取数（断点续跑）
conda run -n jaycode python -m research.alpha compile --name a_x --expr "rank(-r_20d)"  # DSL 编译
conda run -n jaycode python -m research.factorlib list|show <n>|add|set-status|record-eval|exprs
conda run -n jaycode python -m research.sentinel         # 在库因子健康复测（--apply 自动退役）
conda run -n jaycode python -m research.wfo years <因子> --reverse   # 逐年成绩（滚动验证）
conda run -n jaycode python -m research.wfo rotate a:rev b:rev       # 滚动年度选枪
conda run -n jaycode python -m research.signals                     # 每日荐股 Top-10（含自动补编译滞后产物）
bash research/dig_supervisor.sh &            # dig 监工（cron 每 30min 保活；PAUSE_DIG 旗标=暂停；状态看 data/derived/dig_supervisor.log）
bash research/dig_health.sh                  # dig 健康哨兵（cron 每 30min；监工+cron 双哑火的兜底，异常写 data/derived/dig_health.log）
conda run -n jaycode python -m research.wfo_screen [因子...]  # 候选批量 WFO 清洗（断点续跑，判决在 derived/wfo_screen.jsonl）
conda run -n jaycode python -m research.famcorr  # 全体 active 因子血缘矩阵（derived/famcorr.json，截面≥300 保护）
```
```
