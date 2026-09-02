# -*- coding: utf-8 -*-
"""research —— 因子 Loop 引擎工作区（提炼/验证层）。

第一阶段（数据底座）模块：
    config.py      路径统一读取（raw_dir / derived_dir / jqcli_bin）
    jq_channel.py  聚宽云端取数通道（jqcli 三段式 + 认证 fail-fast + 交易日历）
    fetch.py       取数任务（calendar / probe / daily / auction，分片断点续跑）
"""
