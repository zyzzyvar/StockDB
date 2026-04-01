# StockDB Task Board

当前无进行中的任务。

---

## 已完成任务

### [2026-03-20] 修复每日自动更新缺失问题
- [x] 补录 adj_factor（2026-03-19/20，共 10983 行）
- [x] 补录 top_list（2026-03-20，58 行）
- [x] 新增 `fetch_adj_factor_by_date()` — 按日全市场一次获取
- [x] 新增 `load_adj_factor_by_date()` — 对应 loader
- [x] `update_one_day()` 加入 adj_factor 步骤
- [x] `update_one_day()` 加入 margin_detail T+1 补录逻辑
- [x] 修复 margin_detail / top_list loader：空数据也写 data_update_log
- [x] launchd 触发时间从 17:30 改为 18:30
- [x] 重载 launchd 任务

**结果：** 明日起每日任务将完整覆盖所有表，包含 T+1 margin_detail 自动补录。
