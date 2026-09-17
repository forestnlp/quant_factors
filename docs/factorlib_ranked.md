# 因子库全量名册（按战绩排序）

> 生成：2026-09-17（机器生成，源=`factorlib.json` + `wfo_screen.jsonl`；重生成：`PYTHONPATH=. conda run -n jaycode python data/derived/gen_factor_doc.py`）
> 成绩口径：k=100、rebal=10、band(0.10,0.50]、含费、WFO 逐年向前。
> ⚠ 本档是快照；权威账本永远是 `data/derived/factorlib.json`。

**在册 214 支**（产品 3 + 候选 211）；其中 36 支上过 WFO 全量回测（第一梯队，按 Sharpe 排序），178 支过入门质检未上全量回测（第二梯队，按入册时间排序）。

## 原料与算子词典

| 原料列 | 含义 |
|---|---|
| r_1 / r_5 / r_20 / r_60d | 1/5/20/60 日收益率（后复权收盘） |
| v_amt_5_20 | 近5日均额 / 近20日均额（量能热度，>1=放量） |
| v_corr_pv_20 | 量价 20 日相关（正=放量涨/缩量跌，"跟势"） |
| v_std_20 | 20 日收益波动率 |
| v_vwap_dev | 收盘价对当日 VWAP 偏离 |
| v_close_loc | 收盘在当日高低区间中的位置（0~1） |
| auc_* | 集合竞价列（额占比/量比等，撮合价=开盘价，量才是信息） |
| mf_* | 资金流列（主力/大单净流入占比） |
| fin_* | 财务 PIT 列（np_yoy 净利同比、rev_yoy 营收同比、gross 毛利、cash 现金质量、goodwill 商誉…） |
| ind_* | 行业 PIT 列（ind_r_20d 行业20日动量、ind_rs_20d 相对强弱、ind_amt_5_20 行业量能热度、ind_lead_20 板块内领先度） |
| unl_* | 解禁 PIT 列（未来解禁股本占比/日历热度） |
| pb_ratio / pe_ratio | 市净率 / 市盈率 |
| high_limit / low_limit | 当日触涨停 / 跌停（0/1） |

| 算子 | 含义 |
|---|---|
| rank(x) | 日截面百分位名次（0~1，横截面"只要名次不要数值"） |
| delta(x, n) | x 与 n 日前的差 |
| ts_sum / ts_max / ts_min / ts_rank / ts_corr / decay_linear(x, n) | n 日滚动和/极值/名次/相关/线性衰减 |
| sign(x) / abs(x) | 符号 / 绝对值 |

## 第一梯队 · WFO 全量回测 36 支（按 Sharpe 降序）

### 1. a_small_value
- **战绩**：年化 +18.2% / Sharpe +0.78（含费，2020 起全区间）｜ 1 原料 ｜ 入册 2026-09-09
- **计算方式**：`rank(-vlm_ln_circ) * rank(-pb_ratio)`
- **计算原理**：机构追逐大票与高景气赛道，低流通市值且低市净的公司被流动性折价与忽视错杀，我赚取折价收敛的钱。

### 2. a_limitup_cold_rev
- **战绩**：年化 +16.7% / Sharpe +0.77（含费，2020 起全区间）｜ 2 原料 ｜ 入册 2026-09-09
- **计算方式**：`rank(-ts_sum(high_limit, 20)) * rank(-r_20d)`
- **计算原理**：散户追逐连板/涨停热度，导致高涨停数股票短期拥挤、未来回报差；叠加20日跌幅较大的冷落股，赌无人注意的超跌均值回归，我赚追涨停散户的钱。

### 3. a_pe_cash_quality
- **战绩**：年化 +13.3% / Sharpe +0.76（含费，2020 起全区间）｜ 2 原料 ｜ 入册 2026-09-09
- **计算方式**：`rank(-pe_ratio) * rank(fin_cash_quality)`
- **计算原理**：高现金质量但低估值的公司因缺乏热门叙事被市场错误抛弃，赚价值修复与安全边际的钱。

### 4. a_cash_cold_limit
- **战绩**：年化 +15.5% / Sharpe +0.75（含费，2020 起全区间）｜ 2 原料 ｜ 入册 2026-09-09
- **计算方式**：`rank(fin_cash_asset) * rank(-ts_mean(high_limit, 20))`
- **计算原理**：现金资产充裕但近月很少涨停的股票未被爆炒，兼具抗风险与价值回归收益。

### 5. a_np_goodwill_limit_cool
- **战绩**：年化 +14.7% / Sharpe +0.75（含费，2020 起全区间）｜ 3 原料 ｜ 入册 2026-09-10
- **计算方式**：`rank(fin_np_yoy) * rank(-fin_goodwill_eq) * rank(-ts_mean(high_limit, 20))`
- **计算原理**：净利增长且商誉低的公司若近期少涨停，则是被热点忽略的真成长

### 6. a_opm_cold_limit_lowturn
- **战绩**：年化 +13.5% / Sharpe +0.74（含费，2020 起全区间）｜ 2 原料 ｜ 入册 2026-09-10
- **计算方式**：`rank(fin_opm) * rank(-ts_sum(low_limit, 20)) * rank(-vlm_turnover)`
- **计算原理**：零售资金把盈利质量好但近期少跌停、换手低迷的股票错杀成冷门票，低流动性使定价修正延后，我赚后续关注度回流的钱。

### 7. a_goodwill_limit_cool
- **战绩**：年化 +15.3% / Sharpe +0.73（含费，2020 起全区间）｜ 2 原料 ｜ 入册 2026-09-10
- **计算方式**：`rank(-fin_goodwill_eq) * rank(-ts_mean(high_limit, 20))`
- **计算原理**：高商誉且近期频繁涨停会吸引散户追高，随后在并购兑现压力与热度退潮下更容易回落；低商誉且无涨停热度者更少接盘踩踏。

### 8. a_lowpb_quiet_corr
- **战绩**：年化 +14.3% / Sharpe +0.73（含费，2020 起全区间）｜ 2 原料 ｜ 入册 2026-09-09
- **计算方式**：`rank(-pb_ratio) * rank(-v_corr_pv_20)`
- **计算原理**：低PB且量价相关性低的个股便宜且未被资金同步追逐，修复被忽视的错价；赚追逐放量趋势的散户的钱。

### 9. a_quality_calm_vol
- **战绩**：年化 +12.7% / Sharpe +0.71（含费，2020 起全区间）｜ 2 原料 ｜ 入册 2026-09-09
- **计算方式**：`rank(fin_cash_quality) * rank(-v_std_20)`
- **计算原理**：现金质量高但波动安静的公司被短线注意力资金忽视，后续由基本面资金修复。

### 10. a_low_debt_no_panic
- **战绩**：年化 +15.3% / Sharpe +0.70（含费，2020 起全区间）｜ 2 原料 ｜ 入册 2026-09-09
- **计算方式**：`rank(-fin_debt) * rank(-ts_sum(low_limit, 20))`
- **计算原理**：低负债公司不经历流动性强平，过去20日几乎无跌停的错杀/防御票更可能修复。

### 11. a_np_low_panic
- **战绩**：年化 +14.2% / Sharpe +0.70（含费，2020 起全区间）｜ 2 原料 ｜ 入册 2026-09-10
- **计算方式**：`rank(fin_np_yoy) * rank(-ts_sum(low_limit, 20))`
- **计算原理**：净利高增长且近20日跌停恐慌稀少，说明基本面能吸收恐慌，赚错杀修复的钱

### 12. a_cash_quality_low_pv_corr
- **战绩**：年化 +13.1% / Sharpe +0.69（含费，2020 起全区间）｜ 2 原料 ｜ 入册 2026-09-10
- **计算方式**：`rank(fin_cash_quality) * rank(-v_corr_pv_20)`
- **计算原理**：现金流质量稳定但价量相关性低的个股未被散户追涨资金盯上，错误定价来自注意力不足，修复其低关注度带来的折价可赚散户忽略高质量的钱。

### 13. a_pe_no_limit
- **战绩**：年化 +13.5% / Sharpe +0.67（含费，2020 起全区间）｜ 2 原料 ｜ 入册 2026-09-09
- **计算方式**：`rank(-pe_ratio) * rank(-ts_sum(high_limit, 20))`
- **计算原理**：低估值股票若近20日无涨停吸引散户炒作，价值回归且投机退潮，可赚追涨资金的钱

### 14. a_gross_rev_limit_cool
- **战绩**：年化 +13.4% / Sharpe +0.67（含费，2020 起全区间）｜ 3 原料 ｜ 入册 2026-09-10
- **计算方式**：`rank(fin_gross) * rank(fin_rev_yoy) * rank(-ts_sum(high_limit, 20))`
- **计算原理**：高毛利且收入增长的公司若近期涨停稀少、情绪冷淡，被过度冷落后的机构/散户共同忽视产生错杀，我赚其基本面被低估修复的钱

### 15. a_np_low_goodwill_cold_auc
- **战绩**：年化 +13.3% / Sharpe +0.66（含费，2020 起全区间）｜ 3 原料 ｜ 入册 2026-09-10
- **计算方式**：`rank(fin_np_yoy) * rank(-fin_goodwill_eq) * rank(-auc_money_share)`
- **计算原理**：低商誉的高净利增长未被竞价资金追逐，避开并购泡沫溢价并赚认知偏差的钱

### 16. fin_cash_quality
- **战绩**：年化 +12.4% / Sharpe +0.63（含费，2020 起全区间）｜ 1 原料 ｜ 入册 2026-09-02
- **计算方式**：`fin_cash_quality`
- **计算原理**：经营现金流TTM/|净利TTM|：利润有现金backing->未来收益高（现金为王）

### 17. auc_money_share
- **战绩**：年化 +13.1% / Sharpe +0.63（含费，2020 起全区间）｜ 1 原料 ｜ 入册 2026-09-02
- **计算方式**：`auc_money_share`
- **计算原理**：竞价成交额占全日比：竞价抢筹是噪声，占比高->未来收益低

### 18. a_retail_calm_corr
- **战绩**：年化 +12.3% / Sharpe +0.62（含费，2020 起全区间）｜ 2 原料 ｜ 入册 2026-09-10
- **计算方式**：`rank(-mf_net_pct_l) * rank(-v_corr_pv_20)`
- **计算原理**：散户在高关注度时净买入追涨导致后续回报偏低；做多低散户净买入且量价相关性安静的股票，赚散户情绪错定价的钱。

### 19. a_goodwill_calm_vwap
- **战绩**：年化 +13.1% / Sharpe +0.61（含费，2020 起全区间）｜ 2 原料 ｜ 入册 2026-09-10
- **计算方式**：`rank(-fin_goodwill_eq) * rank(-v_vwap_dev)`
- **计算原理**：商誉虚高公司若还偏离VWAP易被资金抛弃，低商誉且贴线成交才有安全边际。

### 20. a_cash_asset_low_pv
- **战绩**：年化 +11.2% / Sharpe +0.61（含费，2020 起全区间）｜ 2 原料 ｜ 入册 2026-09-09
- **计算方式**：`rank(fin_cash_asset) * rank(-ts_std(r_1, 20))`
- **计算原理**：...

### 21. a_cheap_low_mv
- **战绩**：年化 +13.7% / Sharpe +0.61（含费，2020 起全区间）｜ 1 原料 ｜ 入册 2026-09-09
- **计算方式**：`rank(-pe_ratio) * rank(-vlm_ln_mv)`
- **计算原理**：机构因流动性约束忽视微小盘，低市盈率提供估值安全垫，赚覆盖不足导致的错误定价的钱

### 22. a_pe_cool_recent_bb
- **战绩**：年化 +14.1% / Sharpe +0.61（含费，2020 起全区间）｜ 1 原料 ｜ 入册 2026-09-09
- **计算方式**：`rank(-pe_ratio) * rank(-ts_mean(bb_yest, 5))`
- **计算原理**：低市盈率且不靠最近涨停/连板吸引眼球，散户追逐板效应导致便宜无炒作者被错误定价，我赚追高者的钱

### 23. a_pe_cool_corr
- **战绩**：年化 +11.3% / Sharpe +0.61（含费，2020 起全区间）｜ 2 原料 ｜ 入册 2026-09-09
- **计算方式**：`rank(-pe_ratio) * rank(-v_corr_pv_20)`
- **计算原理**：低估值且价量相关性低，说明未被短期资金合力追高，更安静。

### 24. a_quiet_two
- **战绩**：年化 +11.2% / Sharpe +0.61（含费，2020 起全区间）｜ 1 原料 ｜ 入册 2026-09-08
- **计算方式**：`rank(-auc_money_share) * rank(-vlm_turnover)`
- **计算原理**：回喂第2轮：独立双信号(auc相关<=0.25)交互=最安静组合(竞价无人抢筹+全天低换手)；教训应用:交互合成在ICIR量级相近(0.71/0.47)时才有效

### 25. a_oversold_cold_vwap
- **战绩**：年化 +12.7% / Sharpe +0.61（含费，2020 起全区间）｜ 2 原料 ｜ 入册 2026-09-09
- **计算方式**：`rank(-r_60d) * rank(-v_vwap_dev)`
- **计算原理**：长期跌幅大且日内收盘低于均价的股票，情绪出清、关注度低，存在过度反应后的均值回复收益。

### 26. a_goodwill_cool_corr
- **战绩**：年化 +12.0% / Sharpe +0.60（含费，2020 起全区间）｜ 2 原料 ｜ 入册 2026-09-10
- **计算方式**：`rank(-fin_goodwill_eq) * rank(-v_corr_pv_20)`
- **计算原理**：高商誉股票常被并购故事和量价共振吸引散户追涨，未来减值与踩踏风险使高值端差，做多低商誉且无量价共振的标的。

### 27. a_oversold_cold_corr
- **战绩**：年化 +12.0% / Sharpe +0.60（含费，2020 起全区间）｜ 2 原料 ｜ 入册 2026-09-09
- **计算方式**：`rank(-r_60d) * rank(-v_corr_pv_20)`
- **计算原理**：60日跌幅大且量价相关性低的个股未被资金持续追逐，错杀后存在均值回归

### 28. a_quiet_close_strength
- **战绩**：年化 +10.7% / Sharpe +0.60（含费，2020 起全区间）｜ 1 原料 ｜ 入册 2026-09-09
- **计算方式**：`rank(ts_mean(v_close_loc, 5)) * rank(-vlm_turnover)`
- **计算原理**：尾盘收强且低换手说明上涨由惜售而非散户放量追高推动，未来更可能延续。

### 29. a_retail_calm_vol
- **战绩**：年化 +10.7% / Sharpe +0.59（含费，2020 起全区间）｜ 2 原料 ｜ 入册 2026-09-10
- **计算方式**：`rank(-mf_net_pct_l) * rank(-v_std_20)`
- **计算原理**：散户资金未流入且波动收敛时，卖压释放、注意力低，未来更可能修复

### 30. a_lowpb_smooth_auc
- **战绩**：年化 +11.1% / Sharpe +0.58（含费，2020 起全区间）｜ 2 原料 ｜ 入册 2026-09-09
- **计算方式**：`rank(-pb_ratio) * rank(-ts_mean(auc_imb, 5))`
- **计算原理**：低估值且近期竞价买盘失衡被平滑剔除，散户追高抢筹被抑制，错杀修复。

### 31. a_main_corr_quiet
- **战绩**：年化 +10.0% / Sharpe +0.53（含费，2020 起全区间）｜ 2 原料 ｜ 入册 2026-09-09
- **计算方式**：`rank(mf_net_pct_main) * rank(-v_corr_pv_20)`
- **计算原理**：主力净流入但价量相关低时，吸筹并非散户跟风推动，而是独立资金错杀布局；我赚跟风盘滞后追涨的钱。

### 32. a_pb_auc_cool
- **战绩**：年化 +9.4% / Sharpe +0.51（含费，2020 起全区间）｜ 2 原料 ｜ 入册 2026-09-09
- **计算方式**：`rank(-pb_ratio) * rank(-auc_imb)`
- **计算原理**：散户竞价抢筹会推高贵价，我买低估值且竞价资金不拥挤的股票，赚注意力错配导致的低估回归钱。

### 33. a_main_inflow_short_oversold
- **战绩**：年化 +10.1% / Sharpe +0.51（含费，2020 起全区间）｜ 2 原料 ｜ 入册 2026-09-09
- **计算方式**：`rank(mf_net_pct_main) * rank(-r_5d)`
- **计算原理**：主力净流入且短期下跌时，散户恐慌抛售被机构承接，我赚后续错杀修复。

### 34. a_gross_cold_nopause
- **战绩**：年化 +9.2% / Sharpe +0.50（含费，2020 起全区间）｜ 2 原料 ｜ 入册 2026-09-10
- **计算方式**：`rank(fin_gross) * rank(-ts_mean(bb_yest, 20)) * rank(-ts_mean(paused, 20))`
- **计算原理**：高毛利率公司在竞价资金撤离、无停牌异常时，被短线情绪资金错误当成冷门风险忽略，配置资金修复其定价错误。

### 35. a_main_auc_cool
- **战绩**：年化 +8.8% / Sharpe +0.47（含费，2020 起全区间）｜ 2 原料 ｜ 入册 2026-09-09
- **计算方式**：`rank(mf_net_pct_main) * rank(-1 * auc_money_share)`
- **计算原理**：主力净流入但竞价成交占比低，机构低调建仓而散户注意力未至，未来跑赢。

### 36. v_amt_5_20
- **战绩**：年化 +8.9% / Sharpe +0.46（含费，2020 起全区间）｜ 1 原料 ｜ 入册 2026-09-02
- **计算方式**：`v_amt_5_20`
- **计算原理**：放量负向：近5日均额/近20日均额，放量->未来收益低（用户核心信念，L3第三次复现）

## 第二梯队 · 入门质检通过、未上全量回测 178 支

（这些枪过了 IC/ICIR 质检门入池，是 ML 组合器的特征原料；单枪战绩未测——组合层统一考核。表达式与原理照列备查。）

1. **a_rev_x_lowvol** 🏆产品（2原料, 2026-09-08）
   - `rank(-r_20d) * rank(-v_std_20)`
   - 原理：彩排首猎：反转与低波单独封存，但两者同为安静-低位风格，rank乘积交互可能合成更强暴露
2. **a_retail_chase_quiet** 🏆产品（1原料, 2026-09-08）
   - `rank(-mf_net_pct_l) * rank(-vlm_turnover)`
   - 原理：散户净买入占比高且换手放大代表追涨接盘，散户情绪过热后未来收益更差。
3. **a_quality_quiet** 🏆产品（2原料, 2026-09-09）
   - `rank(fin_cash_quality) * rank(-v_amt_5_20)`
   - 原理：现金流质量×缩量清淡：利润有现金 backing 且无人关注的低调股
4. **a_value_auc_cool**（2原料, 2026-09-10）
   - `rank(-pe_ratio) * rank(-auc_money_share)`
   - 原理：散户在竞价端追逐高估值热点，低估值且竞价资金冷清的票被忽略，后续估值修复带来超额收益。
5. **a_lever_calm_corr**（3原料, 2026-09-10）
   - `rank(-fin_debt) * rank(-v_corr_pv_20) * rank(-v_std_20)`
   - 原理：低杠杆、价量关联低、波动低的公司不易被强平踩踏和短线资金错杀，散户注意力追逐会低估其稳定性
6. **a_debt_return_dev_calm**（3原料, 2026-09-10）
   - `rank(-fin_debt) * rank(-ts_std(r_1, 20)) * rank(-v_vwap_dev)`
   - 原理：散户和杠杆资金追逐高波动与日内偏离，忽视低财务杠杆且价格路径安静、收盘贴近VWAP的稳健标的，导致其被错误折价。
7. **a_quality_oversold_nolimit**（3原料, 2026-09-10）
   - `rank(-r_20d) * rank(fin_cash_quality) * rank(-ts_sum(low_limit, 20))`
   - 原理：20日超跌中散户恐慌卖出，但现金流质量高且几乎没有连续跌停的公司往往被错杀，后续随情绪修复获得正收益。
8. **a_main_quiet_clean_goodwill**（2原料, 2026-09-10）
   - `rank(mf_net_pct_main) * rank(-ts_mean(vlm_turnover, 20)) * rank(-fin_goodwill_eq)`
   - 原理：主力资金在低换手、商誉泡沫小的票上低调吸筹，赚追涨散户和高商誉故事盘的钱
9. **a_gross_lowvol_value**（3原料, 2026-09-10）
   - `rank(-pb_ratio) * rank(fin_gross) * rank(-v_std_20)`
   - 原理：低估值、高毛利且低波动的冷门公司易被机构忽视，后续存在均值回归与盈利支撑修复
10. **a_auc_bid_cool**（1原料, 2026-09-10）
   - `rank(-delta(auc_money_share, 20)) * rank(-ts_mean(bb_yest, 20))`
   - 原理：竞价资金占比与昨日抢筹溢价同时回落，说明散户注意力退潮，避免追高导致的中期错误定价被修复。
11. **a_quality_corr_limit_fade**（4原料, 2026-09-10）
   - `rank(fin_rev_yoy + fin_gross) * rank(-delta(v_corr_pv_20,20)) * rank(-ts_sum(high_limit,10))`
   - 原理：...
12. **a_retail_chase_corr**（2原料, 2026-09-10）
   - `rank(-ts_corr(r_1, mf_net_pct_l, 20))`
   - 原理：散户净买入与当日涨幅越相关，说明散户在追涨，这类追逐错误未来收益更差，我买相关性低者赚散户错杀钱。
13. **a_lowpb_auc_stable**（2原料, 2026-09-10）
   - `rank(-ts_std(auc_imb, 20)) * rank(-pb_ratio)`
   - 原理：散户追逐高波动竞价失衡的高价股，我买估值低且竞价情绪稳定的低估冷门。
14. **a_profit_growth_quality_calm_post**（2原料, 2026-09-10）
   - `rank(fin_np_yoy - fin_rev_yoy) * rank(-ts_std(post_close / delay(post_close, 1), 20))`
   - 原理：投资者追逐营收增速却忽略增收不增利，做多利润增速超过营收增速且盘后波动低者，赚高收入叙事兑现失败者的钱。
15. **a_cash_goodwill_stable_turn**（2原料, 2026-09-10）
   - `rank(fin_cash_asset - fin_goodwill_eq) * rank(-ts_std(vlm_turnover, 20))`
   - 原理：高现金低商誉的真资产公司若换手不躁动，散户炒作退潮后价格向基本面回归
16. **a_pb_post_calm**（1原料, 2026-09-10）
   - `rank(-pb_ratio) * rank(-ts_std(post_close / delay(post_close, 1), 20))`
   - 原理：低估值且收盘后价格波动平静的股票，赚取短线融资与情绪资金高估后回吐的钱
17. **a_goodwill_post_calm**（1原料, 2026-09-10）
   - `rank(-fin_goodwill_eq) * rank(-ts_std(post_close / delay(post_close, 1), 20))`
   - 原理：低商誉公司没有并购虚值包袱，若收盘后价格波动安静则说明未被短线噪声关注，错误定价由注意力驱动的散户造成
18. **a_limit_corr_cold**（2原料, 2026-09-10）
   - `rank(-ts_sum(high_limit, 20)) * rank(-v_corr_pv_20)`
   - 原理：频繁涨停且价量高相关的股票会被动量追逐推高，买回未过热、价量未共振的股票能吃到情绪退潮后的均值回归。
19. **a_limit_amt_cold**（2原料, 2026-09-10）
   - `rank(-ts_sum(high_limit, 20)) * rank(-v_amt_5_20)`
   - 原理：近20日涨停热度越低且近期成交相对萎缩的股票越被散户忽略，冷门缩量带来后续收益。
20. **a_small_net_cash_quiet**（3原料, 2026-09-10）
   - `(rank(fin_cash_asset) + rank(-fin_debt)) * rank(-vlm_ln_circ) * rank(-v_std_20)`
   - 原理：小流通市值且净现金、低波动的个股关注度不足且流动性折价显著，未来存在被重估的均值回复空间。
21. **a_profit_fade_oversold_no_panic**（4原料, 2026-09-10）
   - `rank(fin_np_yoy - fin_rev_yoy) * rank(-r_60d) * rank(-ts_sum(low_limit, 60))`
   - 原理：盈利增速高于营收增速说明利润率改善而非虚胖，若股价60日超卖且无跌停出清，市场尚未定价其修复。
22. **a_low_goodwill_calm_mv_shrink**（2原料, 2026-09-11）
   - `rank(-fin_goodwill_eq) * rank(-delta(vlm_ln_mv, 60)) * rank(-ts_mean(paused, 20))`
   - 原理：并购故事靠商誉放大，散户/游资在市值已缩水、停牌风险高的低质小票里继续追逐易被减值和流动性冲击套牢；做多低商誉且市值未大幅缩水的冷静票。
23. **a_goodwill_mv_shrink_nolimit**（2原料, 2026-09-11）
   - `rank(-fin_goodwill_eq) * rank(-delta(vlm_ln_mv, 120)) * rank(-ts_sum(low_limit, 20))`
   - 原理：低商誉、市值收缩且近期无跌停恐慌的公司，并购泡沫与错杀恐慌被出清，后续修复被追逐商誉题材和恐慌盘的散户遗漏。
24. **a_auc_post_cool_nopause**（2原料, 2026-09-11）
   - `rank(-auc_imb) * rank(-(log(post_close) - delay(log(post_close), 5))) * rank(-ts_sum(paused, 60))`
   - 原理：竞价买压弱且盘后价格已冷却、无停牌的股票，短线冲动未抢筹造成的价格错压会被均值回归修复，赚钱来自追涨散户的延迟退坡。
25. **a_profit_value_vwap_fade**（5原料, 2026-09-11）
   - `rank(fin_np_yoy - fin_rev_yoy) * rank(-pb_ratio) * rank(-delta(v_vwap_dev, 20)) * rank(-v_amt_5_20)`
   - 原理：盈利增速超过营收增速的公司若成交降温且成交均价溢价回落，说明热度消退但基本面质量改善，后续由价值发现收益。
26. **a_profit_value_corr_calm**（4原料, 2026-09-11）
   - `rank(fin_np_yoy - fin_rev_yoy) * rank(-pb_ratio) * rank(-v_corr_pv_20) * rank(-ts_mean(st_flag, 20))`
   - 原理：盈利增速跑赢收入增速且市净率低，但价量相关性低，说明基本面改善未被趋势资金跟进，赚散户与动量资金冷落错杀的钱。
27. **a_profit_value_auc_calm**（5原料, 2026-09-11）
   - `rank(fin_np_yoy - fin_rev_yoy) * rank(-pb_ratio) * rank(-ts_mean(auc_money_share, 5)) * rank(-ts_mean(paused, 20))`
   - 原理：盈利增速差与低估值在交易关注度与停牌风险低的股票中更易被长期资金吸纳
28. **a_profit_value_pe_corr_calm**（5原料, 2026-09-11）
   - `rank(fin_np_yoy - fin_rev_yoy) * rank(-pe_ratio) * rank(-ts_mean(v_corr_pv_20, 5)) * rank(-ts_mean(paused, 20))`
   - 原理：利润增速高于营收说明真实盈利改善，低PE与低量价相关性代表未被估值/资金热炒，赚盲目追高者的钱
29. **a_main_deep_cool**（3原料, 2026-09-11）
   - `rank(mf_net_pct_main) * rank(-r_60d) * rank(-ts_sum(high_limit, 60))`
   - 原理：深跌后主力仍在净买入但近60日无涨停热度，说明机构在冷落中吸筹而非散户追涨。
30. **a_pe_lowvol_calm**（2原料, 2026-09-11）
   - `rank(-pe_ratio) * rank(-v_std_20)`
   - 原理：低估值股票若同时低波动，说明未被短线资金爆炒，买入便宜且安静的股票赚高估值高波动股的均值回归与散户过度交易折价。
31. **a_auc_low_heat_clean**（5原料, 2026-09-11）
   - `rank(-ts_std(auc_imb, 20)) * rank(-(ts_sum(high_limit, 60) + ts_sum(low_limit, 60))) * rank(fin_cash_asset - fin_debt)`
   - 原理：Auction-order imbalance volatility and frequent limit hits attract retail speculation, while net-cash/clean leverage stocks outperform when this heat fades.
32. **a_main_close_uncoupled_quality**（3原料, 2026-09-11）
   - `rank(mf_net_pct_main) * rank(fin_cash_quality) * rank(-ts_corr(mf_net_pct_main, v_close_loc, 20))`
   - 原理：主力资金在现金质量较好的票上安静吸筹、不跟随收盘抢筹，零售追逐日内强势收盘导致后续回落，我赚零售的错误。
33. **a_roe_clean_cold_fade**（4原料, 2026-09-11）
   - `rank(fin_roe_ttm) * rank(-fin_goodwill_eq) * rank(-delta(v_amt_5_20, 20)) * rank(-ts_sum(high_limit, 20))`
   - 原理：高ROE低商誉但热度/放量正在退潮时，机构偏好基本面硬而散户不再追高，未来更容易被修复。
34. **a_low_volume_return_chase**（1原料, 2026-09-11）
   - `rank(-ts_corr(r_1, vlm_turnover, 20)) * rank(-ts_mean(vlm_turnover, 20))`
   - 原理：散户把放量与短线上涨同步当作有效信号而追涨，量价高度耦合的股票透支未来收益；低换手且量价脱敏的冷门被忽视，聪明钱赚这种注意力错配的钱。
35. **a_amt_spike_netcash_quiet**（3原料, 2026-09-11）
   - `rank(-ts_max(vlm_turnover, 20)) * rank(fin_cash_asset - fin_debt) * rank(-ts_max(high_limit, 20))`
   - 原理：散户追逐单日放量/涨停的流动性事件，这类股票未来易反转；我买入现金充足、无资金和情绪冲击的平稳公司，赚散户追高者的钱。
36. **a_calm_netcash_jump_fade**（3原料, 2026-09-11）
   - `rank(-ts_max(abs(r_1), 20)) * rank(fin_cash_asset - fin_debt) * rank(-ts_mean(vlm_turnover, 20))`
   - 原理：散户用暴涨暴跌和放量给净现金公司贴情绪溢价/折价，做多未出现极端日内波动、换手不躁且账上净现金的股票以赚其错误定价的钱。
37. **a_st_quiet_corr**（1原料, 2026-09-11）
   - `rank(-ts_mean(st_flag,20))*rank(-v_corr_pv_20)`
   - 原理：避开ST风险与量价同步投机，散户追高风险警示股和量价齐升时犯错。
38. **a_cold_amt_nonspike**（1原料, 2026-09-11）
   - `rank(-ts_mean(vlm_turnover, 20)) * rank(-ts_max(v_amt_5_20, 20))`
   - 原理：散户追逐放量高换手的热点容易接盘，我买低换手且近20日成交额比无脉冲放大的冷门票赚其情绪反噬的钱。
39. **a_float_cold_auc_calm**（2原料, 2026-09-11）
   - `rank(-ts_mean(auc_money_share, 20)) * rank(vlm_ln_circ - vlm_ln_mv) * rank(-ts_std(r_1, 20))`
   - 原理：散户追逐持续高集合竞价资金热度的开盘行情导致热股超买，稳定高自由流通盘且低波动标的被冷落；做多后者赚过度追逐后的均值回归钱
40. **a_lowpb_amt_nonst**（2原料, 2026-09-11）
   - `rank(-pb_ratio) * rank(-v_amt_5_20) * rank(-ts_mean(st_flag, 20))`
   - 原理：散户追逐放量上涨和估值故事，导致低估值且成交金额持续冷却的非ST冷门票被冷落；做多这类均值回归标的可赚追高散户的钱。
41. **a_lowpb_cash_nonst**（2原料, 2026-09-11）
   - `rank(-pb_ratio) * rank(fin_cash_quality) * rank(-ts_mean(st_flag, 20))`
   - 原理：投资者对低估值股票一刀切风险折价，未区分其中现金质量高且非ST的廉价安全资产，我赚错杀便宜货的钱。
42. **a_lowpb_netcash_nonst**（3原料, 2026-09-11）
   - `rank(-pb_ratio) * rank(fin_cash_asset - fin_debt) * rank(-ts_mean(st_flag, 20))`
   - 原理：低 PB 且净现金充足的非 ST 公司被市场错杀为低质，后续估值修复。
43. **a_lowpb_cashgoodwill_calm_pe**（4原料, 2026-09-12）
   - `rank(-pb_ratio) * rank(fin_cash_asset - fin_goodwill_eq) * rank(-ts_std(pe_ratio, 20))`
   - 原理：便宜且现金足以覆盖商誉、估值波动小的股票被追逐热点的散户遗忘，真实资产重估赚钱
44. **a_main_quiet_value_cash**（5原料, 2026-09-12）
   - `rank(-ts_corr(mf_net_pct_main, r_1, 20)) * rank(-pb_ratio) * rank(fin_cash_asset - fin_debt)`
   - 原理：机构资金流入但不跟着股价同步拉升，说明是真吸筹不是拉抬；叠加低PB和净现金，赚散户追逐资金流和热度导致的错价
45. **a_lowpb_tangible_cool**（5原料, 2026-09-12）
   - `rank(-pb_ratio) * rank(fin_cash_asset - fin_goodwill_eq - fin_debt) * rank(-ts_mean(high_limit, 20))`
   - 原理：低PB、净现金资产覆盖商誉与债务的安静标的，因散户追逐涨停热点而被冷落，资产价值存在均值回归。
46. **a_cash_goodwill_limit_fade**（4原料, 2026-09-12）
   - `rank(fin_cash_asset - fin_goodwill_eq) * rank(-ts_sum(high_limit, 20)) * rank(-v_vwap_dev)`
   - 原理：cash-rich low-goodwill firms that are not overheat/overpayed intraday get overlooked
47. **a_cash_quality_cheap_quiet_vwap**（3原料, 2026-09-12）
   - `rank(-pb_ratio)*rank(fin_cash_quality)*rank(-ts_mean(vlm_turnover,20))*rank(-ts_mean(v_vwap_dev,5))`
   - 原理：散户追逐盘中放量拉升的热门票，冷门低PB且现金质量扎实的标的被忽视错卖，我买无人抢筹的便宜硬资产，赚注意力追逐的反向。
48. **a_main_lowvol**（2原料, 2026-09-12）
   - `rank(mf_net_pct_main) * rank(-1 * v_std_20)`
   - 原理：主力资金在低波动、散户噪音较弱的个股中仍有净买入，说明其定价权未被短期情绪完全覆盖；高波动代表散户博弈噪音，未来负alpha。
49. **a_hard_quality_uncrowded_mom**（3原料, 2026-09-12）
   - `rank(fin_cash_quality) * rank(-fin_goodwill_eq) * rank(-ts_max(r_10d, 20))`
   - 原理：趋势散户追逐近10日最大涨幅的热点，硬质量且商誉负担低、尚未被炒作的股票被系统性忽视，等热点退潮或价值重估时赚其回吐与回补的钱。
50. **a_post_calm_auc**（1原料, 2026-09-12）
   - `rank(-ts_std(log(post_close) - delay(log(post_close), 1), 20)) * rank(-auc_imb)`
   - 原理：...
51. **a_no_pv_surge_quiet**（2原料, 2026-09-12）
   - `rank(-ts_corr(r_5d, v_amt_5_20, 20)) * rank(-ts_mean(vlm_turnover, 20))`
   - 原理：当5日收益与相对成交额同步放量走高时，散户情绪追涨接盘、机构借机派发，未来收益转差；做多量价未形成放量拉升且换手持续偏低的股票，赚散户追高犯错的钱。
52. **a_cash_quality_close_vwap_uncouple**（3原料, 2026-09-12）
   - `rank(fin_cash_quality) * rank(-ts_corr(v_close_loc, v_vwap_dev, 20)) * rank(-ts_std(v_vwap_dev, 20))`
   - 原理：散户将日内收盘位置与VWAP偏离的共振当成聪明钱信号，对安静未炒作的现金质量股给折价；做多高现金质量且该共振低、VWAP偏离波动小的股票，赚追涨注意力衰减的钱。
53. **a_close_vwap_uncoupled_auc_quiet**（3原料, 2026-09-12）
   - `rank(-ts_corr(v_close_loc, v_vwap_dev, 20)) * rank(-ts_std(v_vwap_dev, 20)) * rank(-ts_mean(auc_money_share, 5))`
   - 原理：当收盘强度不再依赖当日VWAP溢价且竞价资金集中度低时，日内追逐盘失效、股票以低关注路径运行，未来由基本面定价带来超额收益。
54. **a_amt_calm_uncoupled_val**（3原料, 2026-09-12）
   - `rank(-ts_std(v_amt_5_20,20)) * rank(-v_corr_pv_20) * rank(-ts_std(pb_ratio,20))`
   - 原理：短线资金追逐量价同步且成交与估值剧烈波动的错误定价，做多成交稳定、量价耦合低、估值预期稳定的股票以赚取流动性噪声修正后的均值回归。
55. **a_low_leverage_cold_heat**（1原料, 2026-09-12）
   - `rank(-mt_fin_ratio) * rank(-ts_mean(vlm_turnover, 20)) * rank(-ts_mean(high_limit, 20))`
   - 原理：融资盘、成交与涨停热度同时低温的股票没有被杠杆游资抱团炒作，散户追涨缺乏燃料，后续价格更可能向基本面回归。
56. **a_cash_quality_micro_stable**（3原料, 2026-09-12）
   - `rank(fin_cash_quality)*rank(-ts_std(v_close_loc,20))*rank(-ts_std(v_vwap_dev,20))`
   - 原理：高现金质量公司的日内收盘位置与VWAP偏离长期稳定，说明未被散户追涨噪声扰动；市场低估这类稳健质量，我赚追逐波动者错误定价的钱。
57. **a_cash_quality_low_float_auc_calm**（2原料, 2026-09-12）
   - `rank(fin_cash_quality) * rank(-vlm_ln_circ) * rank(-ts_mean(auc_money_share,20)) * rank(-ts_mean(vlm_turnover,20))`
   - 原理：散户和投机资金在竞价/换手里追逐高流通盘热闹票，高现金质量、低流通盘且竞价冷清的公司被忽略，修复收益由耐心多头赚走。
58. **a_dual_inflow_crowd_cold**（4原料, 2026-09-12）
   - `rank(-ts_corr(relu(mf_net_pct_main), relu(mf_net_pct_l), 20)) * rank(-ts_mean(auc_money_share, 20)) * rank(-ts_sum(high_limit, 20))`
   - 原理：主力和散户同时在资金流上合力抢筹时，集合竞价抢筹与涨停热度会放大散户追高错配；做多资金未合力、竞价冷静且无涨停的标的，赚拥挤反转的钱。
59. **a_calm_board_pause**（2原料, 2026-09-12）
   - `rank(-ts_sum(bb_yest, 20)) * rank(-ts_max(abs(r_5d), 20)) * rank(-ts_mean(paused, 20))`
   - 原理：打板和短线资金追逐昨日连板、大幅跳动和停牌题材，情绪退潮后由接盘者亏损；做多低连板、低短线波动、近期无停牌标的，赚投机拥挤退潮的钱。
60. **a_goodwill_close_cold**（2原料, 2026-09-12）
   - `rank(-fin_goodwill_eq) * rank(-ts_std(v_close_loc, 20)) * rank(-ts_sum(bb_yest, 20))`
   - 原理：低商誉公司没有并购故事，若收盘价在日内振幅中的位置也不忽上忽下且近期很少涨停，说明散户没在抢筹，未来错杀收益好
61. **a_q_rev_auc_calm**（2原料, 2026-09-12）
   - `rank(-r_5d) * rank(-ts_std(auc_imb,20)) * rank(-ts_sum(bb_yest,20))`
   - 原理：短线恐慌卖出的股票若竞价需求稳定且无涨停/异动封板，散户过度杀跌，后续均值回归.
62. **a_float_attention_stability**（1原料, 2026-09-12）
   - `rank(vlm_ln_circ - vlm_ln_mv) * rank(-ts_max(vlm_turnover, 20)) * rank(-ts_std(v_close_loc, 20))`
   - 原理：高流通占比股票的解禁/减持抛压和低流通盘易被炒作性更低；当短线换手尖峰消退且盘中收盘位置稳定时，市场错误忽视这类安静高流通股票，我赚短线注意力追逐者的错定价钱。
63. **a_small_lowpause_lowvol**（2原料, 2026-09-12）
   - `rank(-vlm_ln_mv) * rank(-ts_mean(paused, 20)) * rank(-v_std_20)`
   - 原理：投资者对小市值股的停牌与高波动风险过度折价，稳定低波动、少停牌的小盘被系统性低估
64. **a_small_circ_quiet_pause**（1原料, 2026-09-12）
   - `rank(-vlm_ln_circ) * rank(-ts_mean(vlm_turnover, 20)) * rank(-ts_mean(paused, 20))`
   - 原理：A股散户追逐高换手热门小票，我买流通市值小、低连续换手且极少停牌的交易扰动小盘，赚流动性风险溢价与错误定价修复的钱。
65. **a_small_cash_panic_fade**（3原料, 2026-09-12）
   - `rank(-vlm_ln_circ) * rank(fin_cash_quality) * rank(-ts_mean(paused, 20)) * rank(-delta(ts_sum(low_limit, 10), 10))`
   - 原理：散户对跌停恐慌与停牌风险反应过度，做多现金质量好、无停牌且跌停频率正在下降的小流通盘票，赚风险被错杀的钱。
66. **a_lowpb_float_lowvol**（2原料, 2026-09-12）
   - `rank(-pb_ratio) * rank(vlm_ln_circ - vlm_ln_mv) * rank(-v_std_20)`
   - 原理：散户追逐涨停、解禁与波动故事，低市净率且流通盘已基本出清、波动安静的公司被忽略，买这些赚注意力与供给错配的钱。
67. **a_small_corr_amt_calm**（2原料, 2026-09-12）
   - `rank(-vlm_ln_mv) * rank(-v_corr_pv_20) * rank(-ts_std(v_amt_5_20, 20))`
   - 原理：...
68. **a_float_value_auc_calm**（2原料, 2026-09-12）
   - `rank(-pb_ratio) * rank(vlm_ln_circ - vlm_ln_mv) * rank(-ts_std(auc_money_share, 20))`
   - 原理：散户过度追逐竞价资金异动与投机热度，忽视可流通比重相对更高、开盘资金参与平静的便宜股，导致这类低关注价值股的估值折价未被及时修复。
69. **a_main_vwap_absorb**（4原料, 2026-09-12）
   - `rank(-ts_corr(mf_net_pct_main, v_vwap_dev, 20)) * rank(-v_std_20) * rank(-ts_sum(low_limit, 20))`
   - 原理：主力在均价下方吸筹（资金流与日内贴水同向为负）且股票低波动、无跌停恐慌时，散户把盘中贴均价误认为弱势，未来修复。
70. **a_quality_stable_cash_turn**（2原料, 2026-09-13）
   - `rank(fin_cash_quality) * rank(-ts_std(fin_cash_asset, 60)) * rank(-ts_mean(vlm_turnover, 20))`
   - 原理：现金流质量高且现金余额稳定的公司被低换手的忽视定价错配，散户追逐故事而非稳定现金。
71. **a_cash_quality_vwap_discount_low_r10_vol**（3原料, 2026-09-13）
   - `rank(fin_cash_quality) * rank(-v_vwap_dev) * rank(-ts_std(r_10d, 20))`
   - 原理：散户追逐日内高于均价和近端波动放大的强势票，忽视现金质量稳定且处于日内折价、近10日波动收敛的标的，我赚短线资金注意力错配的钱。
72. **a_main_stable_auc_vwap**（3原料, 2026-09-13）
   - `rank(ts_mean(mf_net_pct_main,20)) * rank(-ts_std(mf_net_pct_main,20)) * rank(-ts_mean(auc_money_share,5)) * rank(-ts_mean(v_vwap_dev,5))`
   - 原理：主力稳定净流入且价格低于均价、盘后竞价未被散户追高时，机构建仓尚未扩散，赚散户后知后觉的钱
73. **a_main_stable_cool_corr**（3原料, 2026-09-13）
   - `rank(ts_mean(mf_net_pct_main, 20)) * rank(-ts_std(mf_net_pct_main, 20)) * rank(-ts_mean(high_limit, 20)) * rank(-v_corr_pv_20)`
   - 原理：主力持续稳定流入但尚未被涨停情绪和放量跟涨资金发现时，机构吸筹形成价格真空，我赚游资与散户后知后觉追入的钱。
74. **a_quiet_clean_calm**（2原料, 2026-09-13）
   - `rank(-ts_mean(vlm_turnover,20))*rank(-ts_std(v_close_loc,20))*rank(-ts_mean(st_flag,20))*rank(-ts_mean(paused,20))`
   - 原理：散户在高换手、尾盘忽强忽弱的问题ST/停牌股上错误追逐，我选择低换手、尾盘稳定、非ST非停牌的安静股票赚他们的钱
75. **a_float_quality_limit_cool**（3原料, 2026-09-13）
   - `rank(fin_cash_quality) * rank(vlm_ln_circ - vlm_ln_mv) * rank(-(ts_std(high_limit,20)+ts_std(low_limit,20)))`
   - 原理：散户追逐筹码锁定和涨跌停彩票票，自由流通盘更大、涨跌停波动更低且现金质量高的安静票被错杀，我赚注意力退潮和均值回归的钱。
76. **a_cold_peak_nopanic**（1原料, 2026-09-13）
   - `rank(-ts_max(bb_yest, 20)) * rank(-ts_mean(vlm_turnover, 20)) * rank(-ts_sum(low_limit, 60))`
   - 原理：短线情绪资金追逐板块热度峰值、高换手和跌停恐慌，会把这些高热度高恐慌票透支；我买板块热度峰值低、成交安静且长期少跌停的冷门安全票，赚他们追涨杀跌后的流动性折价修复。
77. **a_cold_amt_auc_calm**（3原料, 2026-09-13）
   - `rank(-ts_max(v_amt_5_20, 20)) * rank(-ts_sum(low_limit, 60)) * rank(-ts_std(auc_imb, 20))`
   - 原理：短线资金会追逐放量冲高、恐慌跌停和竞价异动，导致近20日未现极端放量、近60日几乎无跌停且开盘竞价情绪稳定的冷门股票被错误冷落；做多这类票赚情绪资金追涨杀跌犯错的钱。
78. **a_cost_eff_cold_auc_calm**（4原料, 2026-09-13）
   - `rank(fin_opm - fin_gross) * rank(-ts_mean(high_limit, 20)) * rank(-ts_std(auc_money_share, 20))`
   - 原理：投资者追逐高收入增长与涨停题材而忽视毛利率到经营利润率之间的费用损耗；我买入费用效率更高、但涨停热度低且竞价资金波动平静的公司，赚注意力错配与后续均值回归的钱。
79. **a_bottom_sink_cool**（3原料, 2026-09-13）
   - `rank(ts_min(v_close_loc, 60)) * rank(-ts_sum(high_limit, 60)) * rank(-ts_std(r_10d, 20))`
   - 原理：散户在低涨停、低波动的窄幅震荡中因缺乏赚钱效应而离场，日K下沿承接稳定者由机构锁筹，未来容易补涨。
80. **a_low_turn_close_impact_cash**（2原料, 2026-09-13）
   - `rank(-ts_corr(vlm_turnover, v_vwap_dev, 20)) * rank(fin_cash_quality) * rank(-ts_mean(vlm_turnover, 20))`
   - 原理：当换手放大伴随收盘相对VWAP偏离越大，说明短线资金用流动性冲击价格，散户追逐这类标的接盘；现金流质量高且换手平稳的低价冲击标的少被噪音推动，更可能赚取均值回归。
81. **a_clean_cost_no_spike**（4原料, 2026-09-13）
   - `(rank(fin_cash_asset - fin_goodwill_eq) + rank(fin_opm - fin_gross)) * rank(-ts_max(vlm_turnover, 20))`
   - 原理：短线资金追逐高热度与毛利率叙事，忽视费用率黑洞与商誉减值，导致成交无脉冲但现金充足、经营利润率损失小的冷门股被错误低估；我赚这些散户注意力追逐者的钱。
82. **a_quality_cost_cold_volume**（5原料, 2026-09-13）
   - `rank(fin_cash_quality) * rank(fin_opm - fin_gross) * rank(-v_std_20) * rank(-ts_sum(high_limit, 20))`
   - 原理：现金质量好且成本效率高的公司若成交波动与涨停热度都低，说明尚未被热钱定价，我赚追逐热点资金的钱。
83. **a_cost_eff_float_vwap_calm**（3原料, 2026-09-13）
   - `rank(fin_opm - fin_gross) * rank(-ts_std(v_vwap_dev, 20)) * rank(vlm_ln_circ - vlm_ln_mv)`
   - 原理：散户追逐日内VWAP热度并偏好低流通盘炒作，忽略成本效率稳定且流通充裕的公司，买这类公司赚日内追逐者和流动性错杀者的钱。
84. **a_clean_cost_float_board_cold**（5原料, 2026-09-13）
   - `rank(fin_cash_asset - fin_goodwill_eq - fin_debt) * rank(fin_opm - fin_gross) * rank(vlm_ln_circ - vlm_ln_mv) * rank(-ts_mean(bb_yest, 20))`
   - 原理：资产负债表干净且成本效率高的公司若近期无涨停/连板热度且自由流通盘充足，会被短线资金错杀，随后真实盈利修复；赚游资追板资金的钱。
85. **a_lowpb_closevol_calm**（2原料, 2026-09-13）
   - `rank(-pb_ratio) * rank(-ts_corr(v_close_loc, vlm_turnover, 20)) * rank(-ts_mean(vlm_turnover, 20))`
   - 原理：散户把尾盘放量拉成强势收盘当作买入信号，低PB且尾盘位置与成交无关的冷门票被忽视，未来修复来自追尾盘错判的散户
86. **a_cost_quiet_clean_fade**（6原料, 2026-09-13）
   - `rank(fin_cash_asset - fin_goodwill_eq - fin_debt) * rank(fin_opm - fin_gross) * rank(-ts_mean(vlm_turnover, 20)) * rank(-ts_sum(low_limit, 60))`
   - 原理：低成本厚现金股票在无跌停恐慌且成交安静时未被投机资金定价，我赚忽视基本面安全垫的短线资金的钱
87. **a_retail_vwap_uncoupled_calm**（3原料, 2026-09-13）
   - `rank(-ts_corr(mf_net_pct_l, v_vwap_dev, 20)) * rank(-ts_std(auc_imb, 20)) * rank(-ts_std(v_vwap_dev, 20))`
   - 原理：散户资金若与日内VWAP溢价同向放大往往是在追涨接盘，选择散户流入与日内溢价关联弱、竞价与日内价格扰动均平稳的个股，赚追涨散户后续犯错的钱。
88. **a_ret_flow_decoupled_quiet**（3原料, 2026-09-13）
   - `rank(-ts_corr(r_1, mf_net_pct_l, 20)) * rank(-ts_std(auc_imb, 20)) * rank(-ts_std(vlm_turnover, 20))`
   - 原理：散户资金流与日收益耦合弱、盘口和成交都稳定时，价格未被追涨杀跌噪声扭曲，我赚散户追逐资金流犯错的钱。
89. **a_auc_turn_decoupled_quiet**（2原料, 2026-09-13）
   - `rank(-abs(ts_corr(auc_imb, vlm_turnover, 20))) * rank(-ts_mean(vlm_turnover, 20)) * rank(-ts_sum(low_limit, 20))`
   - 原理：散户会把竞价买卖压力信号机械地追逐到成交放大中，形成短暂拥挤，因此竞价失衡与换手率高度同步且放量、跌停恐慌明显的股票未来容易被兑现，我们赚的是这群追逐者错定价的钱。
90. **a_slow_trend_cool_auc**（4原料, 2026-09-13）
   - `rank(r_60d) * rank(v_corr_pv_20) * rank(-ts_mean(auc_money_share, 5)) * rank(-v_std_20)`
   - 原理：在60日温和上行、近20日量价共振但开盘竞价资金未拥挤且波动未放大的股票上，赚散户/游资追逐高竞价抢筹和高波动放量误判强势的钱。
91. **a_trend_pv_aucspike_vwap_calm**（5原料, 2026-09-13）
   - `rank(r_60d - r_20d) * rank(v_corr_pv_20) * rank(-(ts_max(abs(auc_imb), 20))) * rank(-(ts_std(v_vwap_dev, 20)))`
   - 原理：慢趋势且有量价配合时，散户若未在集合竞价制造显著买卖失衡、日内偏离VWAP也稳定，则说明趋势未被短线抢筹污染，未来更可能延续。
92. **a_trend_limit_cool_vwap**（5原料, 2026-09-13）
   - `rank(r_60d - r_20d) * rank(v_corr_pv_20) * rank(-delta(ts_sum(high_limit, 20), 20)) * rank(-ts_std(v_vwap_dev, 20))`
   - 原理：趋势与价量仍在确认、但涨停热度从高位退潮且日内VWAP偏离稳定的股票，拥挤度下降而趋势未破，买入赚追逐涨停热度资金退潮后的延续收益。
93. **a_trend_sync_cold_lowlimit**（4原料, 2026-09-13）
   - `rank(r_60d - r_20d) * rank(v_corr_pv_20) * rank(-ts_mean(vlm_turnover, 20)) * rank(-ts_sum(low_limit, 20))`
   - 原理：短线资金误把低换手但量价同步的中期上涨当作缺乏热度而忽略，后续热度扩散时后知后觉追涨，我们赚这批后追者接盘的钱。
94. **a_mid_trend_pullback_lowvol_sync**（5原料, 2026-09-13）
   - `rank(r_60d - r_20d) * rank(v_corr_pv_20) * rank(-r_5d) * rank(-v_std_20)`
   - 原理：中期上升趋势中5日回调是散户短线恐慌卖出所致，量价同步且波动受控说明资金未走，我赚短线过度反应的钱
95. **a_stable_close_value**（2原料, 2026-09-14）
   - `rank(-pb_ratio) * rank(ts_min(v_close_loc, 20) - ts_max(v_close_loc, 20))`
   - 原理：低PB股票若收盘位置范围窄，说明无短线/尾盘扰动，散户被噪声错杀，我赚追逐尾盘波动资金的钱。
96. **a_cold_auc_goodwill_pe_stable**（3原料, 2026-09-14）
   - `rank(-ts_min(auc_money_share, 20)) * rank(-fin_goodwill_eq) * rank(-ts_std(pe_ratio, 60))`
   - 原理：散户和短线资金会追逐集合竞价热钱并给商誉/估值波动故事过度定价，买入长期竞价冷、低商誉且估值稳定的公司，可赚其注意力追逐与风险低估的钱。
97. **a_lowpb_stable_float_amount**（2原料, 2026-09-14）
   - `rank(-pb_ratio) * rank(-ts_std(vlm_ln_circ - vlm_ln_mv, 60)) * rank(-ts_std(v_amt_5_20, 60))`
   - 原理：散户追逐成交扰动和流通盘结构变化明显的热闹标的，错杀低估值且流通盘比例与成交活跃度长期稳定的个股，我赚追逐热闹者的错价收益。
98. **a_clean_quiet_pe_stable**（2原料, 2026-09-14）
   - `rank(fin_cash_quality) * rank(-ts_max(vlm_turnover, 20)) * rank(-ts_std(pe_ratio, 60))`
   - 原理：...
99. **a_lowpb_cold_clean**（5原料, 2026-09-14）
   - `rank(-pb_ratio) * rank(-ts_max(v_amt_5_20, 20)) * rank(-ts_mean(abs(v_corr_pv_20), 20)) * rank(-ts_mean(high_limit + low_limit, 20))`
   - 原理：散户和游资追逐放量、价量同步且有涨跌停事件的股票使其透支；低PB且长期无成交放大、价量脱耦、无涨跌停事件的公司被遗忘，热钱退潮后价值回归。
100. **a_pe_stable_float_calm**（1原料, 2026-09-14）
   - `rank(-pe_ratio) * rank(-ts_std(vlm_ln_circ - vlm_ln_mv, 60)) * rank(-ts_std(vlm_turnover, 20))`
   - 原理：散户把估值和股本频繁变化的股票误当成机会，追高造成估值/流通扰动；做多低估值、估值与浮动股本都稳定、成交冷清的公司赚流动性折价回归。
101. **a_lowpb_vwap_pe_stable**（3原料, 2026-09-14）
   - `rank(-pb_ratio) * rank(-ts_std(v_vwap_dev, 60)) * rank(-ts_std(pe_ratio, 60))`
   - 原理：散户追逐日内大幅折溢价和估值跳变的故事股，忽略便宜且价格/估值波动平稳的股票；我买低PB、低VWAP偏离波动、低PE波动，赚无人问津的流动性折价与价值回归。
102. **a_tangible_value_vwap_stable**（5原料, 2026-09-14）
   - `rank(fin_cash_asset - fin_goodwill_eq - fin_debt) * rank(-pe_ratio) * rank(-ts_std(v_vwap_dev, 60))`
   - 原理：投机资金追逐高杠杆和高商誉故事，硬资产净现金低PE的冷门公司被冷落；VWAP波动平稳说明未被短线资金反复扰动，赚其情绪错价修复的钱。
103. **a_rev_growth_calm_no_board**（4原料, 2026-09-14）
   - `rank(fin_rev_yoy) * rank(-v_std_20) * rank(-ts_mean(high_limit, 20)) * rank(-ts_mean(low_limit, 20))`
   - 原理：高营收增速在低波动且无涨停跌停的平静环境中出现，说明不是短线资金爆炒，持有可赚过度交易者的钱
104. **a_main_post_calm**（1原料, 2026-09-14）
   - `rank(ts_mean(mf_net_pct_main, 20)) * rank(-ts_std(mf_net_pct_main, 20)) * rank(-ts_std(log(post_close) - delay(log(post_close), 1), 20))`
   - 原理：主买资金持续流入且盘后价格波动低，说明机构吸筹未引发盘后恐慌抛售，未来更易修复；我赚盘后过度反应散户的钱。
105. **a_cold_auc_vwap_limit**（3原料, 2026-09-14）
   - `rank(-ts_mean(auc_money_share, 20)) * rank(-ts_std(v_vwap_dev, 20)) * rank(-ts_mean(high_limit, 20))`
   - 原理：散户追逐竞价抢筹、日内VWAP波动和涨停热点会短期透支股价，我们做多这三类热度同时冷却的平稳股票赚其热度退潮后的收益。
106. **a_cold_auc_turn_panic**（2原料, 2026-09-14）
   - `rank(-ts_std(auc_imb, 20)) * rank(-ts_mean(vlm_turnover, 20)) * rank(-ts_sum(low_limit, 20))`
   - 原理：竞价失衡稳定、换手冷淡且近期无跌停恐慌的股票未被情绪资金追涨杀跌，我买入这些安静标的，赚散户放量抢筹与恐慌抛售的高买低卖的钱
107. **a_board_vol_vwap_cold**（2原料, 2026-09-14）
   - `rank(-ts_sum(bb_yest, 20)) * rank(-ts_max(v_std_20, 20)) * rank(-v_vwap_dev)`
   - 原理：散户和游资追逐近期涨停与放量抢筹、把价格买在VWAP上方形成透支溢价，我买无涨停事件、量能无尖峰且VWAP贴水的安静票，赚追高接盘者的钱。
108. **a_post_auc_decoupled_calm**（2原料, 2026-09-14）
   - `rank(-ts_corr(log(post_close) - delay(log(post_close), 1), auc_money_share, 20)) * rank(-ts_mean(auc_money_share, 20)) * rank(-ts_mean(paused, 20))`
   - 原理：短线资金若追逐盘后价格与竞价资金热度同步的标的会过度反应，做多两者脱耦、竞价热度低且未停牌的股票可从其回落赚钱。
109. **a_float_cold_auc_stable**（1原料, 2026-09-14）
   - `rank(vlm_ln_mv - vlm_ln_circ) * rank(-ts_mean(auc_money_share,20)) * rank(-ts_std(vlm_ln_circ,60))`
   - 原理：散户追逐竞价放量和高自由流通的热门票，忽视限售比例高、流通盘稳定且竞价资金未抢筹的公司；做多被忽略的锁仓低关注度标的。
110. **a_lead_ebb_quality_value**（4原料, 2026-09-14）
   - `rank(-delta(ind_lead_20, 20)) * rank(fin_cash_quality) * rank(-pb_ratio) * rank(-v_std_20)`
   - 原理：我赚追逐板块龙头的钱：板块资金虹吸龙头时，高质量低估值个股被抽血错跌，龙头热度退潮后这些冷门价值股会补涨修复。
111. **a_lead_ebb_lowpb_lowindvol**（3原料, 2026-09-14）
   - `rank(-delta(ind_lead_20, 20)) * rank(-pb_ratio) * rank(-ts_std(ind_r_20d, 20))`
   - 原理：行业龙头相对强度退潮时，低PB且行业波动平稳的成分容易被资金退潮错杀，赚行业追涨资金犯错的钱。
112. **a_lead_slow_cheap_goodwill_cold**（4原料, 2026-09-14）
   - `rank(-delta(ind_lead_20, 60)) * rank(-pb_ratio) * rank(-fin_goodwill_eq) * rank(-ts_sum(high_limit, 20))`
   - 原理：行业主题热度退潮后，散户和游资会对高商誉、高估值、近期涨停过热的股票杀估值，做多其中PB低、商誉占比低且涨停热度已降温的个股，赚追逐热点资金在行业见顶后仍忽视安全边际与减值风险的钱。
113. **a_sector_laggard_hard_cash**（6原料, 2026-09-14）
   - `rank(rank(ind_amt_5_20) - rank(v_amt_5_20)) * rank(fin_cash_asset - fin_goodwill_eq - fin_debt) * rank(-ts_mean(paused,20))`
   - 原理：行业成交热度上升而个股相对冷清时，散户追逐龙头而错杀有净现金、低商誉低杠杆且可交易的滞后价值股，我赚资金轮动错配的钱
114. **a_unl_cold_value_no_st**（3原料, 2026-09-14）
   - `rank(-pb_ratio) * rank(-ts_mean(unl_today, 20)) * rank(-ts_mean(st_flag, 20)) * rank(-ts_mean(paused, 20))`
   - 原理：短线与龙虎榜资金追逐事件热度，低PB但未进入热榜且非ST/未停牌的便宜个股被暂时忽视，价值资金随后修复错误定价。
115. **a_next_unlock_quiet_limit**（3原料, 2026-09-14）
   - `rank(-unl_next20) * rank(-ts_mean(v_vwap_dev, 20)) * rank(-ts_sum(high_limit, 20)) * rank(-ts_mean(st_flag, 20))`
   - 原理：未来解禁供给少、盘中相对成交均价不高且近期无涨停热度的非ST股票，散户追逐与供给抛压均弱，后续价格修复赚情绪退潮的钱。
116. **a_unl_quality_corr_decouple**（4原料, 2026-09-14）
   - `rank(-unl_sum20) * rank(fin_cash_quality) * rank(-abs(ts_mean(v_corr_pv_20,20))) * rank(-ts_mean(paused,20))`
   - 原理：低近期解禁供给且现金质量高、量价相关性弱的股票，赚解禁恐慌和量价噪音错杀优质公司的钱。
117. **a_unl_vwap_quiet_stable**（2原料, 2026-09-14）
   - `rank(-ts_mean(unl_today, 20)) * rank(-ts_std(v_vwap_dev, 20)) * rank(-ts_mean(vlm_turnover, 20)) * rank(-ts_mean(st_flag, 20))`
   - 原理：解禁持有者与散户在供给扰动和量价噪声中错卖低解禁、低换手且日内价偏离稳定的股票，我买被错杀的干净筹码。
118. **a_unlock_decoupled_board_quiet**（3原料, 2026-09-15）
   - `rank(-ts_mean(unl_next20, 20)) * rank(-abs(ts_corr(v_close_loc, v_vwap_dev, 20))) * rank(-ts_mean(bb_yest, 20)) * rank(-ts_mean(st_flag, 20))`
   - 原理：散户和游资追逐板热题材而忽视未来解禁供给，做多低未来解禁、日内价量路径解耦且非板热的安静股可赚其错定价的钱。
119. **a_quiet_supply_cold**（2原料, 2026-09-15）
   - `rank(-ts_mean(auc_money_share, 20)) * rank(-ts_max(vlm_turnover, 20)) * rank(-unl_next20)`
   - 原理：未来解禁供给压力小、竞价资金持续冷却且近月换手峰值低的股票，赚的是解禁与短线资金在高流动性幻觉下追逐筹码并推高价格所犯错的钱。
120. **a_pe_cold_unlock_no_amt**（3原料, 2026-09-15）
   - `rank(-pe_ratio)*rank(-ts_max(v_amt_5_20,20))*rank(-unl_next20)`
   - 原理：投资者为近期放量、解禁供给和估值溢价支付成本，低估但量能不扩张且未来解禁压力小的股票被错杀，买入赚取注意力追逐与供给错配的钱。
121. **a_supply_cold_quiet_pv**（3原料, 2026-09-15）
   - `rank(-ts_mean(unl_next20, 20)) * rank(-ts_max(v_amt_5_20, 20)) * rank(-ts_mean(v_corr_pv_20, 20))`
   - 原理：散户追逐解禁前放量且价量共振的热门股，未来解禁供给会砸盘，我买未来解禁压力低、成交尖峰低、价量关联弱的冷门修复。
122. **a_supply_heat_corr_cold**（3原料, 2026-09-15）
   - `rank(-ts_mean(unl_next20, 20)) * rank(-ts_mean(high_limit, 20)) * rank(-ts_mean(abs(v_corr_pv_20), 20))`
   - 原理：没有未来解禁供给、远离涨停热度且量价联动很弱的股票，残余卖压多由事件/流动性卖盘造成，基本面买盘赚取其过度反应贴水。
123. **a_cold_indamt_vol**（3原料, 2026-09-15）
   - `rank(-ts_mean(ind_amt_5_20, 20)) * rank(-ts_std(r_10d, 20)) * rank(-ts_mean(high_limit, 20))`
   - 原理：低板块成交热度、个股中短期波动收敛且无涨停投机追逐的股票，尚未被散户/游资资金过度定价，后续更可能有均值回归收益。
124. **a_lowpost_auc_floor**（2原料, 2026-09-15）
   - `rank(-ts_std(post_close / delay(post_close, 1), 20)) * rank(-ts_mean(auc_money_share, 5)) * rank(ts_min(v_close_loc, 20))`
   - 原理：未来20日低盘后波动、早盘竞价资金占比回落且日收盘位置从未被极端砸破的股票，说明隔夜信息扰动和早盘散户抢筹同时退潮，机构承接下更容易修复。
125. **a_post_downside_cold_auc**（2原料, 2026-09-15）
   - `rank(-ts_mean(relu(delay(log(post_close + 1), 1) - log(post_close + 1)), 20)) * rank(-ts_std(auc_imb, 5)) * rank(-ts_max(high_limit, 10))`
   - 原理：散户追逐隔夜强势、竞价异动和涨停热度导致拥挤；做多无下行压力、竞价失衡平稳且无涨停热度的低关注稳定股，赚拥挤资金犯错后的错杀修复。
126. **a_post_floor_vwap_quiet**（2原料, 2026-09-15）
   - `rank(-ts_mean(relu(delay(log(post_close + 1), 1) - log(post_close + 1)), 20)) * rank(ts_min(v_close_loc, 20)) * rank(-ts_max(v_vwap_dev, 20))`
   - 原理：短线资金追逐盘后异动与高VWAP溢价，低估了盘后下行少、收盘位置稳固且低溢价/折价股票的吸筹含义，我赚其追高退潮后补涨的钱。
127. **a_post_cold_auc_indvol**（2原料, 2026-09-15）
   - `rank(-ts_mean(relu(delay(log(post_close + 1), 1) - log(post_close + 1)), 20)) * rank(-ts_std(auc_money_share, 20)) * rank(-ts_std(ind_r_1, 20))`
   - 原理：谁犯错误：追逐热点行业和竞价/盘后异动的人气资金，把盘后稳定、竞价参与平稳、行业日内波动低但因此被忽视的票卖得过头；我赚这些注意力追逐者的钱，做多这类“安静且有真实成交约束”的错杀票。
128. **a_cash_quality_indamt_decoupled_quiet**（3原料, 2026-09-15）
   - `rank(fin_cash_quality) * rank(-abs(ts_corr(r_10d, ind_amt_5_20, 20))) * rank(-ts_mean(vlm_turnover, 20))`
   - 原理：高现金质量个股若近10日涨幅与行业量能正相关度低、且自身成交低迷，说明未被行业资金抱团放大、也没被散户放量追逐，赚行业轮动资金忽视与散户追量犯错的钱。
129. **a_lead_cold_vwap_limit**（3原料, 2026-09-15）
   - `rank(-ts_std(ind_lead_20, 20)) * rank(-ts_mean(abs(v_vwap_dev), 5)) * rank(-ts_mean(high_limit, 20))`
   - 原理：短线资金追逐涨停抢筹和盘中拉抬，导致行业龙头地位稳定、无涨停、贴水极小的安静个股被忽视/错杀，我赚其均值回归。
130. **a_lead_stable_quiet_lowvol**（2原料, 2026-09-15）
   - `rank(-ts_std(ind_lead_20, 20)) * rank(-ts_max(vlm_turnover, 20)) * rank(-ts_std(r_10d, 20))`
   - 原理：散户在行业热点轮动中追逐放量和高波动的龙头或跟风股导致未来预期透支，而行业龙头地位稳定且个股没有成交尖峰与收益高波动的股票较少被资金错配、未来表现更好。
131. **a_main_ind_r1_decoupled_calm**（3原料, 2026-09-15）
   - `rank(-ts_corr(mf_net_pct_main, ind_r_1, 20)) * rank(-ts_mean(vlm_turnover, 20)) * rank(-ts_mean(high_limit, 20))`
   - 原理：主力资金与行业短期日收益相关性低说明未跟随行业热度追涨，再叠加低换手与低涨停拥挤，个股被散户/游资定价压力更小，后续更容易出现低拥挤修复收益。
132. **a_main_r5_uncoupled_cool**（4原料, 2026-09-15）
   - `rank(-ts_corr(mf_net_pct_main, r_5d, 20)) * rank(-v_std_20) * rank(-ts_mean(high_limit, 20))`
   - 原理：主力在低波动、无涨停热的个股中逆短期收益吸筹，散户追5日动量，我赚他们追高后的回流/踩踏
133. **a_main_r10_calm_lowdown**（4原料, 2026-09-15）
   - `rank(-ts_corr(mf_net_pct_main, r_10d, 20)) * rank(-ts_mean(v_amt_5_20, 20)) * rank(-ts_sum(low_limit, 20))`
   - 原理：主力净流入不跟随个股10日涨幅且成交额未异常放大、跌停恐慌稀少，说明资金在散户尚未追涨/恐慌出逃时独立布局，我赚未来散户追高或割肉接盘的钱。
134. **a_main_indlead_decouple_cash_quiet**（4原料, 2026-09-15）
   - `rank(-ts_corr(mf_net_pct_main, ind_lead_20, 20)) * rank(fin_cash_quality) * rank(-v_std_20)`
   - 原理：主力资金与行业领导力背离而流入低波动高现金质量股时，散户仍在追龙头和热度，机构在冷门优质处吸筹，故做多赚散户追高回吐的钱。
135. **a_main_indrs_decoupled_quiet**（3原料, 2026-09-15）
   - `rank(-ts_corr(mf_net_pct_main, ind_rs_20d, 20)) * rank(-ts_mean(vlm_turnover, 20)) * rank(-v_std_20)`
   - 原理：行业动量资金追逐相对强弱时犯错：主力净流入与行业相对强弱脱钩甚至逆势，且股价低波动低换手，说明主力在冷门安静中吸筹，市场尚未注意。
136. **a_main_inflow_indrs_decouple_lowvol**（3原料, 2026-09-15）
   - `rank(ts_mean(mf_net_pct_main, 20)) * rank(-ts_corr(mf_net_pct_main, ind_rs_20d, 20)) * rank(-v_std_20)`
   - 原理：主力资金持续净流入却与板块相对强弱脱钩，散户和趋势资金按行业强弱追涨杀跌，低估逆势吸筹的低波个股。
137. **a_lead_stable_close_cool**（2原料, 2026-09-15）
   - `rank(-ts_std(ind_lead_20, 20)) * rank(ts_min(v_close_loc, 20)) * rank(-ts_sum(bb_yest, 20))`
   - 原理：当行业领导资金轮动噪声低、个股近20日涨停炒作冷、且日内收盘位置持续不弱时，短线热钱追逐板块轮动与涨停题材，错误忽视稳定低关注标的，我赚其过度惩罚冷门稳定股的钱
138. **a_close_vol_absorb_quiet**（2原料, 2026-09-16）
   - `rank(ts_corr(v_close_loc, ts_std(r_10d, 20), 20)) * rank(-ts_mean(vlm_turnover, 20)) * rank(-ts_mean(st_flag, 20))`
   - 原理：在低换手、非ST的安静股票中，日内收盘位置能在短期收益波动放大时仍保持高位（收盘位置与短期波动正相关），说明散户恐慌卖出被惜售盘承接，未来有修复；我赚波动追随卖出的钱。
139. **a_vol_lead_decoupled_cash**（4原料, 2026-09-16）
   - `rank(fin_cash_quality) * rank(-abs(ts_corr(v_amt_5_20, ind_lead_20, 20))) * rank(-v_std_20)`
   - 原理：散户会把个股成交放大同步到行业领动；现金质量硬且成交既不跟随行业领动、收益波动又低的个股是注意力遗漏的错杀候选。
140. **a_quiet_unextended_pv**（3原料, 2026-09-16）
   - `rank(-ts_max(v_vwap_dev, 60)) * rank(-ts_mean(auc_money_share, 20)) * rank(-ts_mean(v_corr_pv_20, 20))`
   - 原理：散户在竞价抢筹并把价格推离VWAP、价量同步走强时容易追高，这类高关注度股票随后因资金退潮而表现差，买入低溢价、低竞价抢筹、价量未同步的股票可赚其犯错的钱。
141. **a_cold_unextended_indamt_corr**（3原料, 2026-09-16）
   - `rank(-ts_max(v_vwap_dev, 60)) * rank(-ts_mean(ind_amt_5_20, 20)) * rank(-ts_mean(abs(v_corr_pv_20), 20))`
   - 原理：行业资金退潮时，散户仍把个股价格推到长期高于VWAP并维持虚假量价协动；买入冷门行业、VWAP未透支且量价弱协动的股票，赚热度退潮后的错杀修复。
142. **a_turn_expand_down_support**（1原料, 2026-09-16）
   - `rank(ts_sum(sign(delta(ts_mean(vlm_turnover, 5), 1)) * (-r_1), 5)) * rank(-ts_max(vlm_turnover, 20))`
   - 原理：成交中枢温和抬升时的下跌有承接，且排除爆量派发，我赚恐慌卖盘割在承接上的钱
143. **a_amt_down_no_unlock_absorb**（3原料, 2026-09-16）
   - `rank(ts_sum(sign(delta(v_amt_5_20, 5)) * (-r_5d), 20)) * rank(-ts_mean(unl_next20, 20)) * rank(-ts_max(v_amt_5_20, 60))`
   - 原理：散户把无未来解禁供给压力下的量增价跌误判为机构派发而割肉，做多被恐慌承接的无供给压力票。
144. **a_indamt_inflow_lowheat_quiet**（4原料, 2026-09-16）
   - `rank(delta(ind_amt_5_20, 20)) * rank(-ts_mean(auc_money_share, 20)) * rank(-ts_sum(high_limit, 20)) * rank(-ts_mean(unl_next20, 20))`
   - 原理：板块资金回流但个股竞价热度、涨停历史和解禁抛压都低，赚散户只追热点、忽略补涨标的的钱
145. **a_ind_hot_unextended_quiet**（2原料, 2026-09-16）
   - `rank(-ts_max(v_vwap_dev, 20)) * rank(ts_mean(ind_r_1, 20)) * rank(-ts_max(vlm_turnover, 20))`
   - 原理：短线资金追逐已放量且价格透支VWAP的行业强势股，忽略行业隔夜热度高但价格未透支VWAP、成交仍冷的滞后个股，做多资金扩散。
146. **a_ind20_quiet_lowvol**（3原料, 2026-09-16）
   - `rank(ts_mean(ind_r_20d, 20)) * rank(-ts_mean(auc_money_share, 20)) * rank(-ts_max(v_std_20, 20))`
   - 原理：行业中军中期趋势仍在、个股自身波动和竞价热度未放大，散户尚未把热度交易过度，我赚后知后觉追高资金的钱
147. **a_ind_rs_stable_lowr5**（2原料, 2026-09-16）
   - `rank(ts_mean(ind_rs_20d, 20)) * rank(-ts_std(ind_rs_20d, 20)) * rank(-ts_std(r_5d, 20))`
   - 原理：行业相对强度稳定且个股短周期噪音低的股票延续性更强，而散户追逐忽强忽弱的热门与高波动个股会形成均值回归，从而给稳定趋势让路。
148. **a_max_pv_vol_cold**（3原料, 2026-09-16）
   - `rank(-ts_max(v_corr_pv_20, 20)) * rank(-v_std_20) * rank(-ts_mean(high_limit, 20))`
   - 原理：量价协动尖峰与高波动来自散户放量追涨/打板，未来差；持续低协动、低波动且无涨停热度的股票被错误冷落，我赚注意力追逐者的钱。
149. **a_pv_cool_lowvol_board**（2原料, 2026-09-16）
   - `rank(-ts_max(v_corr_pv_20, 20)) * rank(-v_std_20) * rank(-ts_mean(bb_yest, 20))`
   - 原理：散户在价量同步冲高和涨停封板时追涨，板热退潮且波动收敛后这些拥挤标的未来更差，做多低同步、低波动、低板热者获利。
150. **a_pvabs_cold_shortvol_lowunlock**（3原料, 2026-09-16）
   - `rank(-ts_max(abs(v_corr_pv_20), 60)) * rank(-ts_std(r_10d, 20)) * rank(-ts_mean(unl_next20, 20))`
   - 原理：在价量协同热度退潮、短期波动降温且未来解禁供给压力低时，散户追高失败或恐慌出逃会把无实质利空的个股错杀，我赚错杀后的修复钱。
151. **a_lowpb_holder_net_indcold**（2原料, 2026-09-16）
   - `rank(-pb_ratio) * rank(ts_mean(hc_in20 - hc_reduce20, 60)) * rank(-ts_mean(ind_amt_5_20, 20))`
   - 原理：低估值股票在行业资金退潮时若股东净增持，说明内部人在冷点买入而追逐热点的资金后知后觉，我赚这些行业跟风资金的钱。
152. **a_lowpb_holder_lead_stable**（2原料, 2026-09-16）
   - `rank(-pb_ratio) * rank(ts_mean(hc_in20 - hc_reduce20, 60)) * rank(-ts_std(ind_lead_20, 20))`
   - 原理：...
153. **a_lowpb_holder_newpledge**（1原料, 2026-09-16）
   - `rank(-pb_ratio) * rank(ts_mean(hc_in20 - hc_reduce20, 60)) * rank(-ts_max(pg_new20, 20))`
   - 原理：产业资本用净增持确认低估值，新增质押峰值少意味着未来强制平仓抛压低，其他投资者低估这种安全边际。
154. **a_quality_lead_turn_support**（3原料, 2026-09-16）
   - `rank(fin_cash_quality) * rank(ts_sum(sign(delta(ts_mean(vlm_turnover, 5), 1)) * (-r_5d), 20)) * rank(-ts_std(ind_lead_20, 20))`
   - 原理：现金质量高且板块龙头地位稳定时，放量下跌多为止损/流动性错杀而非基本面恶化，赚散户恐慌卖出的钱。
155. **a_pledge_light_quality_calm**（3原料, 2026-09-16）
   - `rank(fin_np_yoy - fin_rev_yoy) * rank(-pg_ratio) * rank(-ts_mean(pg_new20, 20)) * rank(-v_std_20)`
   - 原理：高质押且持续新增质押的续命杠杆股东在波动中易被平仓或被迫让渡折价，做多低质押、新增质押少、利润增速优于营收增速且波动受控的公司，赚质押盘错杀的钱。
156. **a_indamt_holder_lowpledge_calm**（2原料, 2026-09-16）
   - `rank(ts_mean(ind_amt_5_20, 60)) * rank(-v_std_20) * rank(ts_mean(hc_in20, 60) - ts_mean(hc_reduce20, 60)) * rank(-ts_mean(pg_new20, 20))`
   - 原理：行业资金持续升温时，若个股价格低波动、股东净增持且无新增质押，散户因未见个股放量/质押新闻而忽视供给安全的补涨机会，我赚后知后觉者的钱。
157. **a_chip_pledge_indamt_vwap_calm**（2原料, 2026-09-16）
   - `rank(ts_mean(hc_in20 - hc_reduce20, 60)) * rank(-ts_mean(pg_new20, 20)) * rank(ts_mean(ind_amt_5_20, 20)) * rank(-ts_std(v_vwap_dev, 60))`
   - 原理：股东增持且新增质押少，在行业成交活跃但个股价格路径未过热时，质押和减持恐慌造成的流动性折价会修复，我赚恐慌卖出者的钱
158. **a_pvcool_indstable_clean_limit**（6原料, 2026-09-16）
   - `rank(-ts_mean(abs(v_corr_pv_20), 20)) * rank(-ts_std(ind_r_20d, 20)) * rank(fin_cash_asset - fin_goodwill_eq - fin_debt) * rank(-ts_mean(high_limit, 20))`
   - 原理：散户追逐量价共振与涨停热度，量价脱钩、行业收益平稳、资产负债表干净且少触板的股票被错杀，赚其过度反应的钱。
159. **a_calm_amt_indstable_limit**（4原料, 2026-09-16）
   - `rank(-ts_max(v_amt_5_20, 20)) * rank(-v_std_20) * rank(-ts_std(ind_r_20d, 20)) * rank(-ts_mean(high_limit, 20))`
   - 原理：散户和游资追逐放量冲高、高波动与涨停躁动，我买量能不冲高、个股波动低、行业走势平稳且少涨停的票，赚情绪过热冷却后的低风险补涨。
160. **a_pvcool_indstable_auc_lowvol**（4原料, 2026-09-16）
   - `rank(-ts_mean(abs(v_corr_pv_20), 20)) * rank(-ts_std(ind_r_20d, 20)) * rank(-v_std_20) * rank(-ts_mean(abs(auc_imb), 5))`
   - 原理：行业波动稳定但个股价量同步冷却、日常波动低、竞价无抢筹时，散户板块追逐盘低估其被冷落的安全边际，做多它赚高PV高波追涨资金退潮的钱。
161. **a_cash_quality_vwacool_indstable_lowvol**（4原料, 2026-09-16）
   - `rank(fin_cash_quality) * rank(-ts_mean(v_vwap_dev, 20)) * rank(-ts_std(ind_r_20d, 20)) * rank(-v_std_20)`
   - 原理：现金质量硬、价格围绕VWAP不过热、行业相对表现稳且个股低波，赚追逐热点和情绪波动者的钱。
162. **a_cold_vwap_vol_pledge_low**（2原料, 2026-09-16）
   - `rank(-ts_max(v_vwap_dev, 60)) * rank(-ts_max(v_std_20, 20)) * rank(-ts_mean(pg_ratio, 20))`
   - 原理：做多长期未透支VWAP、近期无波动率尖峰且质押压力低的公司，赚高波动追高散户与高质押股东被迫卖出的钱。
163. **a_indstable_cold_supply_cash**（3原料, 2026-09-17）
   - `rank(-ts_std(ind_r_20d, 20)) * rank(-unl_next20) * rank(-ts_mean(bb_yest, 20)) * rank(fin_cash_quality)`
   - 原理：行业波动和涨停投机冷却时，未来解禁少且现金质量硬的股票常被‘无故事’资金错杀，我赚低供给高质量标的被情绪低估的钱
164. **a_indstable_cold_supply_profit**（4原料, 2026-09-17）
   - `rank(-ts_std(ind_r_20d, 20)) * rank(-ts_mean(unl_next20, 20)) * rank(-ts_mean(bb_yest, 20)) * rank(fin_np_yoy - fin_rev_yoy)`
   - 原理：当行业波动低、涨停热度低、未来解禁供给低时，净利增速跑赢营收增速说明盈利改善来自利润率而非烧钱扩张，我赚在热点轮动与供给冲击中追涨杀跌的散户的钱。
165. **a_indlead_cold_supply_profit**（4原料, 2026-09-17）
   - `rank(-ts_std(ind_lead_20, 20)) * rank(-ts_mean(unl_next20, 20)) * rank(-ts_mean(bb_yest, 20)) * rank(fin_np_yoy - fin_rev_yoy)`
   - 原理：在行业龙头地位稳定、未来解禁供给低且昨日涨停情绪冷清的真实盈利改善股票上，恐慌或冷门资金错杀其基本面，我买入等待筹码稳定后的重估修复。
166. **a_indrs_chip_light_profit**（3原料, 2026-09-17）
   - `rank(-ts_std(ind_rs_20d, 20)) * rank(fin_np_yoy - fin_rev_yoy) * rank(-ts_max(hc_reduce20, 20)) * rank(-ts_max(pg_new20, 20))`
   - 原理：在行业相对收益平静的阶段，利润增速明显超过收入增速、且近期几乎无大股东减持/新增质押的公司，会被市场按供给风险和冷门情绪过度折价；我们赚的是干净盈利质量重新定价的钱。
167. **a_lead_stable_quality_pledge_cool**（4原料, 2026-09-17）
   - `rank(-ts_std(ind_lead_20,60)) * rank(fin_np_yoy - fin_rev_yoy) * rank(-ts_mean(pg_ratio,20)) * rank(-ts_mean(abs(v_corr_pv_20),20))`
   - 原理：趋势资金追逐行业热度脉冲和杠杆质押供给，却忽视盈利增速差与质押风险；行业地位稳定、利润增速高于收入增速、质押负担轻且量价不同步的股票在热度退潮时被错杀，我赚热度资金和质押供给被动抛售的钱。
168. **a_indamt_post_profit_pledge**（4原料, 2026-09-17）
   - `rank(-ts_std(log(post_close + 1) - delay(log(post_close + 1), 1), 20)) * rank(-ts_std(ind_amt_5_20, 20)) * rank(fin_np_yoy - fin_rev_yoy) * rank(-ts_max(pg_new20, 20)) * rank(-ts_max(high_limit, 20))`
   - 原理：散户和情绪资金追逐涨停热点与质押解禁噪音，忽略盘后价格平稳、行业资金流稳定、盈利增长快于收入且新增质押压力小的低噪音错杀标的，我赚他们错卖稳定改善公司的钱。
169. **a_lead_supply_profit_newpledge**（4原料, 2026-09-17）
   - `rank(-ts_std(ind_lead_20, 60)) * rank(fin_np_yoy - fin_rev_yoy) * rank(-unl_next20) * rank(-ts_max(pg_new20, 20))`
   - 原理：市场恐慌未来解禁和新增质押卖压，错杀板块龙头地位稳定、利润增速显著跑赢收入增速的股票；我做多低解禁/低新增质押的稳定真龙头，赚卖压错杀后的修复收益。
170. **a_closevol_uncoupled_cold**（4原料, 2026-09-17）
   - `rank(-ts_corr(v_close_loc, v_std_20, 20)) * rank(-ts_mean(auc_money_share, 20)) * rank(-ts_mean(high_limit, 20)) * rank(-ts_mean(st_flag, 20))`
   - 原理：散户在波动放大时追涨收盘强势、竞价热钱与涨停热度，因此买入收盘强度与波动脱钩、竞价和涨停热度均冷且非ST的股票，赚追涨资金高买的钱。
171. **a_pv_sectorlead_decoupled_cold**（4原料, 2026-09-17）
   - `rank(-ts_corr(v_corr_pv_20, delta(ind_lead_20, 5), 20)) * rank(-ts_mean(auc_money_share, 20)) * rank(-ts_mean(high_limit, 20)) * rank(-ts_mean(st_flag, 20))`
   - 原理：游资/散户在板块领涨时推升个股量价共动，板块动能退潮后这类追涨筹码被杀；做多量价共动不跟随板块领涨动能、且竞价热度与涨停热度低、非ST的错杀承接股。
172. **a_lowpb_auc_pv_cold**（3原料, 2026-09-17）
   - `rank(-pb_ratio) * rank(-ts_mean(auc_money_share, 20)) * rank(-ts_max(v_corr_pv_20, 20))`
   - 原理：低估值股票若未被集合竞价资金抢筹、价量也未同步升温，未来将由被忽视的基本面价值修复；做多低PB+低竞价关注+低价量协动，赚竞价与价量跟随者退潮及忽视错杀的钱。
173. **a_pb_supply_fade_pv**（3原料, 2026-09-17）
   - `rank(-pb_ratio) * rank(-ts_max(abs(v_corr_pv_20), 20)) * rank(-ts_max(pg_new20, 20)) * rank(-ts_mean(unl_next20, 20))`
   - 原理：低PB且价量联动峰值、新增质押与未来解禁供给都很低时，便宜不是强平/解禁砸出的价值陷阱，赚情绪与供给压力消退后的价值修复。
174. **a_pb_supply_lever_quiet**（2原料, 2026-09-17）
   - `rank(-pb_ratio) * rank(-ts_mean(unl_next20, 20)) * rank(-ts_max(pg_new20, 20)) * rank(-ts_mean(mt_fin_ratio, 20))`
   - 原理：低PB股票若近期解禁、新增质押和融资比例都低，则缺乏解禁、质押、两融三类强制卖盘，情绪错杀的便宜筹码更易被耐心资金承接。
175. **a_hardcash_indr1stable_supplylight**（6原料, 2026-09-17）
   - `rank(log(relu(fin_cash_asset - fin_goodwill_eq - fin_debt) + 1) - vlm_ln_mv) * rank(-ts_std(ind_r_1, 20)) * rank(-v_std_20) * rank(-ts_max(pg_new20, 20)) * rank(-ts_mean(unl_next20, 20))`
   - 原理：净有形现金市值比高的硬资产公司，若所在行业短线波动稳定、个股低波动且没有新增质押与未来解禁供给，会被追逐行业波动的短线资金和融资盘错杀，我赚的是被迫供给与注意力错置的钱。
176. **a_pb_margin_chase_fade_supply**（4原料, 2026-09-17）
   - `rank(-pb_ratio) * rank(-ts_sum(relu(delta(ts_mean(mt_fin_ratio, 5), 1) * relu(r_5d)), 20)) * rank(-ts_mean(unl_next20, 20)) * rank(-ts_max(v_vwap_dev, 20))`
   - 原理：低PB股票中剔除融资余额随上涨快速追高的杠杆追逐、并选择VWAP溢价低且未来解禁供给轻者，赚杠杆散户和追涨资金后续被迫去杠杆的钱。
177. **a_pb_cash_supply_indamt_stable**（4原料, 2026-09-17）
   - `rank(-pb_ratio) * rank(fin_cash_quality) * rank(-ts_mean(unl_next20, 20)) * rank(-ts_std(ind_amt_5_20, 20))`
   - 原理：低估值且现金质量扎实的公司，若未来解禁供给有限、行业资金流稳定，则供给折价被错误夸大，价格会向基本面修复。
178. **a_cheap_quality_light_pledge_stable_industry**（5原料, 2026-09-17）
   - `rank(-pb_ratio) * rank(rank(fin_roe_ttm) + rank(fin_gross)) * rank(-ts_mean(pg_new20, 20)) * rank(-ts_std(ind_rs_20d, 20)) * rank(-v_std_20)`
   - 原理：热钱和量化资金拥挤在行业强弱剧烈波动、新增质押与波动放大的热门票，导致便宜且盈利稳定、无新增质押压力且行业相对表现平稳的公司被流动性忽视，我们赚的是这类安静资产价值修复中被热钱配置不足和质押供给恐慌错杀的钱。

## 组合层使用方式

单枪不直接下单（产品枪 a_rev_x_lowvol 除外）。全部在册枪日截面 rank 后喂 XGBoost/LightGBM 逐年向前合成 mlb 打分，band(0.10,0.50] 内 选高分端——组合数字（RankIC≈0.115、同窗 Sharpe 0.7~0.71）见 PROJECT.md。