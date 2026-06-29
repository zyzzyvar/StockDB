# Lessons Learned

每次被用户纠正后在此记录，防止重复犯同类错误。

---

## 数据工程

### L01 — loader 空数据时必须写日志
**错误：** `if df.empty: return 0` 直接返回，不写 `data_update_log`，导致每日检查看起来"缺失"，实则是静默跳过。
**规则：** loader 无论数据是否为空，成功路径都必须调用 `log_update()`，以便后续审计和补录判断。

### L02 — 新 loader 函数必须同步加入 daily_update.py
**错误：** `adj_factor` loader 存在但从未加入 `update_one_day()`，导致复权因子长期不更新。
**规则：** 新增任何 `load_xxx_by_date()` 函数时，立即检查 `scripts/daily_update.py` 是否已包含该步骤。

### L03 — T+1 数据必须明确标注发布时间
**错误：** `margin_detail`（融资融券）是 T+1 数据，当天 18:30 前拿不到，但代码按当日查询，永远返回空。
**规则：** 每个数据接口需明确发布时机（当日盘后 / T+1），对 T+1 数据要在次日任务中补录前日数据。

### L04 — launchd 触发时间要与数据发布时间匹配
**错误：** 17:30 触发时龙虎榜（top_list）尚未发布（约 18:00），导致每日空数据。
**规则：** 触发时间应留有余量，当前设为 18:30；如未来某接口仍频繁空数据，需调查其实际发布时间。

---

## 环境 / 基础设施

### L05 — launchd 任务必须使用项目专属 venv
**错误①：** plist 中写 `/usr/bin/python3`（系统 Python），无已安装包，导致 `ModuleNotFoundError`。
**错误②（2026-05-11）：** plist 写 `/usr/local/bin/python3`（浮动符号链接），Homebrew 升级 Python 3.13→3.14 后链接指向新版，旧版包（loguru 等）全部失效，日志断更 **19 天**才被发现。
**规则（最终方案）：** 在项目根创建 `.venv`（`python3.13 -m venv .venv`），plist 写 `.venv/bin/python` 的绝对路径。venv 内 Python 路径独立于 Homebrew 符号链接，升级后不受影响；依赖通过 `requirements.txt` 锁定。修改 plist 后必须 unload/load 重载。

### L06 — psql 需要手动加 PATH
**规则：** Postgres.app 的 bin 目录不在系统 PATH，需在 `~/.zshrc` 中添加：
`export PATH="/Applications/Postgres.app/Contents/Versions/16/bin:$PATH"`
