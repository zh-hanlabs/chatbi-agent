#!/usr/bin/env python3
"""devflow —— 项目全生命周期管控 CLI（零第三方依赖，仅标准库）。

八个阶段：需求立项 → 方案设计 → 排期计划 → 开发执行 → 代码评审 → 测试验证 → 发布部署 → 复盘归档

常用命令：
    python tools/devflow/devflow.py init --name 我的项目
    python tools/devflow/devflow.py status
    python tools/devflow/devflow.py new requirement --title "秒杀下单限流"
    python tools/devflow/devflow.py check            # 校验当前阶段准出契约
    python tools/devflow/devflow.py gate             # 跑门禁（error 级不通过则返回码 1）
    python tools/devflow/devflow.py phase enter --to design
    python tools/devflow/devflow.py report
完整用法：--help
"""

from __future__ import annotations

import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from lib.cli import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
