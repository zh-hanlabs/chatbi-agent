# {{PROJECT}}

> 由 devflow 初始化生成，请按实际项目补充。

## 项目简介

<!-- TODO: 一句话说清这个项目解决什么问题 -->

## 本地开发

```bash
# 查看当前流程阶段与全景状态
python tools/devflow/devflow.py status

# 校验当前阶段是否满足准出契约（CI 执行同一套命令）
python tools/devflow/devflow.py check
```

## 文档

完整交付物与流程见 [docs/README.md](docs/README.md)：

- 需求：`docs/requirements`
- 设计：`docs/design`、`docs/adr`
- 排期：`docs/plan`
- 评审：`docs/review`
- 测试：`docs/test`
- 发布：`docs/release`
- 复盘：`docs/retro`

## 提交规范

分支：`feature/<需求号>-<简述>`、`fix/<需求号>-<简述>`、`release/vX.Y.Z`
提交：`<type>(<scope>): <简述>`，type ∈ feat / fix / docs / refactor / perf / test / build / ci / chore / revert

## 发布

版本记录见 [CHANGELOG.md](CHANGELOG.md)。项目流程状态存放在 `.devflow/`（务必随代码提交）。
