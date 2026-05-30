## 2026-05-30: 变更日志归档与重建

### 问题描述

当前 `change.md` 累积过长，需要将既有记录归档并重建当前日志入口。

### 修改内容

- 将旧 `change.md` 重命名为 `change（start~2026.5）.md`。
- 新建当前 `change.md`，作为后续任务记录入口。
- 更新 `AGENTS.md`、`CLAUDE.md` 和 YOLO 迁移文档中的相关说明。

### 验证方法

- 使用 `git status -sb`、`rg -n "change.md|change（start~2026.5）.md"` 确认重命名与引用更新。
