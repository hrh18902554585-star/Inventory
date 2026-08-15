# 利润核算 Web 后台服务 — 产品规划 V1.0

> 编制：30 个专题智能体并行调研（代码深挖 10 + 产品设计 10 + 评审验收 10）
> 日期：2026-08-15
> 状态：待评审通过后进入开发

---

## 1. 项目背景与目标

现有利润核算系统是 Tkinter GUI（`gui_batch_query.py`，1805 行单文件），业务人员需在本机运行、手动选文件、等结果。本次将**核算引擎抽取为纯 Python 模块**，包一层 Flask Web 服务（Web 界面 + 异步任务 + 文件上传下载），实现：

- 浏览器（电脑/手机）完成「上传 → 配置 → 处理 → 下载」全流程
- 异步任务 + 实时进度日志，关页面不中断
- 配置表上传管理，订单文件按次上传
- 本地/局域网一键部署，不动现有 GUI（保留兜底）

**成功指标**：操作步骤 ≤5 步（GUI ≥8 步）；任务失败率 ≤2%；新手上手 ≤5 分钟；服务版输出与原 GUI 完全一致。

---

## 2. 产品需求（PRD）

### 2.1 用户画像
电商运营/财务人员，电脑水平一般，电脑 + 手机（局域网 WiFi）访问。

### 2.2 功能分级

| 级别 | 功能 |
|---|---|
| **P0** | 配置表上传管理（成本表/链接表 必填，官补/排序/推广 可选）、订单文件多选上传、Cookie 管理、参数配置（线程数/查税运/排除ID）、异步任务处理、实时进度+日志、结果下载、任务历史 |
| **P1** | 任务历史重跑、24h 结果自动清理、移动端适配、失败明细提示 |
| **P2** | 失败订单仅重查、上传预检（表头即时校验）、缓存导入（复用 GUI 的 tax_cache.json） |

### 2.3 非功能需求
- 单文件上传 ≤10MB，扩展名白名单 + 魔数校验
- 并发任务 2~3 个（超出排队），任务内并发线程默认 2、上限 4
- 结果保留 24h，启动时清扫
- 移动端可用（上传/建任务/看进度/下载四件事）
- 简单访问令牌（防局域网扫描），Cookie 本地存储、日志脱敏

### 2.4 Out of Scope
不做权限系统/多账号、不做定时任务、不做 SSE 推送（轮询足够）、**不改动核算规则本身**（引擎逻辑与原 GUI 逐字一致）。

---

## 3. 系统架构

```
profit_service/
├── engine.py          # ProfitEngine：纯核算引擎（从 gui_batch_query.py 抽取，零 UI 依赖）
├── app.py             # Flask 入口：API 路由 + 上传校验 + 任务调度
├── tasks.py           # 任务管理：ThreadPoolExecutor(2) + 状态机 + 环形日志
├── storage.py         # SQLite 任务库 + tax_cache 原子读写 + 文件管理
├── templates/index.html  # Vue2 + Element UI 单页
├── static/            # 复制自 flask_admin（element-ui 2.15.14 / vue / axios）
├── requirements.txt   # flask / waitress / openpyxl / requests
├── start.bat          # 一键启动
└── data/
    ├── app.db         # tasks + config_files + upload_files
    ├── tax_cache.json # 税运缓存（全局共享 + RLock + 原子写）
    ├── logs/          # app.log（滚动） + tasks/<id>.log
    ├── configs/       # cost/ product_map/ promotion/ subsidy_map/ product_sum/
    ├── uploads/       # 订单文件（清洗原名 + 时间戳，永不覆盖）
    ├── tmp/           # 上传中 .part
    ├── tasks/<job_id>/inputs/   # 订单+配置快照（任务创建时复制）
    └── outputs/<job_id>/        # 任务输出
```

### 3.1 关键解耦（引擎抽取）

`ProfitEngine` 抽取 `BatchQueryApp` 中全部**零 UI 依赖方法** + `process_all_files` 主体，改造点：

| GUI 耦合 | 引擎化 |
|---|---|
| `self.log → root.after` | `log_callback(msg)` 回调注入 |
| `progress_var / status_var` | `progress_callback(pct, text)` |
| 9 个 StringVar/IntVar | `process(source_files, configs, cookie, thread_count, enable_tax, exclude_ids, output_dir)` 参数 |
| `tax_cache` 读写 | 引擎内置 dict，任务结束由 storage 原子落盘 |
| `result_link` | 返回输出文件路径列表 |

**原则：核算逻辑零改动**（含 5 个 load_* 方法、SUMIFS 公式、多天合并、样式规则），保证与原 GUI 输出一致。

### 3.2 一致性保障
`engine.py` 是**唯一事实来源**；GUI 后续改为薄壳调用 engine.py（2~3 天改造，收益：一处修复双端生效）。过渡期约定：GUI 只修 bug 不新增功能。

---

## 4. 技术决策记录（ADR）

| # | 决策 | 结论 | 理由 |
|---|---|---|---|
| ADR-1 | 框架 | ✅ Flask（+waitress） | 已有 flask_admin 代码基础；FastAPI 异步对阻塞式 requests 无收益 |
| ADR-2 | 任务队列 | ✅ 内存 dict + ThreadPoolExecutor(2) + tasks.json 落盘 | Celery/Redis/RQ 单机过度设计；重启后 running 置 error 即可 |
| ADR-3 | 前端通信 | ✅ 2s 轮询 + since 增量 | 任务分钟级，SSE/WebSocket 无必要 |
| ADR-4 | 任务日志 | ✅ 内存 deque(maxlen=5000) + 每任务磁盘文件双写 | tail -f 多任务管理混乱；增量拉取零 IO |
| ADR-5 | 部署 | ✅ waitress（--threads=8） | Windows 原生；**gunicorn 不支持 Windows 必须移除** |
| ADR-6 | 上传文件命名 | ✅ 自写清洗函数保留中文原名 + 时间戳 | 放弃 UUID+meta.json（单点故障+并发写问题）；secure_filename 会剥掉中文 |
| ADR-7 | 配置覆盖 | ✅ 轻量版本化 config_files 表（保留 10 版） | .bak 只有一份无法审计回滚 |
| ADR-8 | 任务快照 | ✅ 任务创建时复制订单+配置到 tasks/<id>/inputs/ | 删源文件不影响历史任务；杜绝跑一半配置被换 |
| ADR-9 | 任务记录 | ✅ SQLite（WAL + busy_timeout + check_same_thread=False） | 重启恢复历史，数据量无压力 |
| ADR-10 | 一致性测试 | ✅ openpyxl 双指针对比（样式+公式文本） | pandas 只能比数据区，比不了排版（排版是核心卖点） |
| ADR-11 | 状态机 | ✅ pending→running→done/error（无 cancelled） | 引擎无法安全中断，取消态无收益 |
| ADR-12 | 静态资源 | ✅ 复制 flask_admin/static | 两系统独立部署，1.1MB 成本可忽略 |

### 4.1 版本与兼容
- **requirements.txt**：`flask>=3.1`、`waitress>=3.0`、`openpyxl==3.1.*`（锁版本）、`requests>=2.32`
- 删 gunicorn（Windows 不支持）、拆 pyinstaller 到 dev 依赖、ttkbootstrap 仅 GUI 用
- Python 3.14 venv 可直接用；openpyxl 的 `wb._sheets = ordered_sheets`（gui_batch_query.py:1779 私有 API）改为 `create_sheet` 顺序控制或 `move_sheet`
- 时区：`datetime.timezone(timedelta(hours=8))` 足够（中国无 DST）；SQLite 存 ISO 带偏移字符串
- 编码：所有 open() 显式 `encoding="utf-8"`；CSV 写文件用 utf-8-sig；日志 FileHandler 指定 utf-8

---

## 5. API 契约

**约定**：BaseURL `/api`；鉴权 `X-Api-Token` 头（静态令牌）；成功 `{"code":0,"data":...}`；错误 `{"code":xxxxx,"message":"中文"}`（HTTP 200，前端按 code 判断）；传输层 401/404/413/500。

**错误码段**：`0xxx` 鉴权通用（0001 未授权/0002 不存在/0003 超限）｜`1xxx` 参数｜`2xxx` 配置类｜`3xxx` 上游 API（3001 Cookie 无效/3002 上游超时）｜`4xxx` 引擎内部。

| 接口 | 说明 |
|---|---|
| `GET /api/cookie` | 返回掩码 + 有效性（**不回传明文**） |
| `POST /api/cookie` | 写入并探测有效性 |
| `GET /api/configs` | 5 类配置当前版本列表 |
| `POST /api/configs/upload` | multipart（type: cost/link/promo/subsidy/sort） |
| `DELETE /api/configs` | 删除/回滚配置版本 |
| `POST /api/uploads` | 订单文件上传（返回文件记录） |
| `GET/DELETE /api/uploads` | 订单文件列表/删除（被 pending/running 任务引用禁止删） |
| `POST /api/jobs` | 创建任务：`{order_files, config_ids, cookie, thread_count, enable_tax, exclude_ids}` |
| `GET /api/jobs` | 历史列表 |
| `GET /api/jobs/<id>?since=N` | 状态 + 进度 + **日志增量**（seq 去重） |
| `GET /api/jobs/<id>/download/<file>` | 结果下载（未完成 409，不存在 404） |
| `POST /api/jobs/<id>/rerun` | 复用参数重跑 |
| `DELETE /api/jobs/<id>` | 清理（仅 done/error，running 409） |
| `GET /api/stats` | 关键指标 |

**上传安全**：文件名清洗（剔除 `\/:*?"<>|` 与控制符、拒绝 `..`、限长 200、保留 CJK）；大小 ≤10MB（413+0003）；xlsx 校验 PK 魔数 + 扩展名一致；同名订单文件自动加时间戳**永不覆盖**，配置文件覆盖并升版本。

---

## 6. 任务生命周期

```
pending ──worker取单──▶ running ──引擎正常返回──▶ done
                          │
                          └──异常/进程中断──▶ error（error 字段 + traceback 落盘，不回传前端）
```

- 线程模型：单例 `ThreadPoolExecutor(max_workers=2)`，超出排队；任务内引擎再开线程池查 API
- 进度：per-task lock 保护 `progress_pct` 与 `logs`；progress 回调合并（>0.3s 才记日志）
- 日志：`deque(maxlen=5000)` 环形 + seq 严格递增；前端 `since` 游标**成功收到后才前进**
- 中断恢复：启动时扫描，凡 running/pending 置 error（"进程中断"），半成品输出删除
- 超时兜底：24h 心跳（last_heartbeat），超时视为挂死置 error
- 清理：DELETE 接口 + 启动清扫 >24h 输出目录；孤儿上传文件 7 天 TTL + 手动清理接口

---

## 7. 前端设计（Vue2 + Element UI 单页）

**三视图**：总览（运行中任务 + 快速新建）/ 新建任务（向导）/ 历史记录。配置管理收编为「配置库」el-drawer 弹层。

### 新建任务向导（4 步）
1. **配置表**：5 类卡片列表（必填红星 + 状态徽标），底部"完成条件"引导条，必填不齐禁用下一步
2. **订单文件**：多选上传，文件卡片带店铺/日期 badge（识别失败标红，提示按 `店铺_日期.xlsx` 规范重命名）
3. **参数**：线程数 slider(2-4)、Cookie textarea（仅提交不持久化浏览器）、查税运 switch、排除ID 标签输入（el-select multiple filterable allow-create）
4. **摘要确认**：文件清单 + 参数快照 → 跳转任务详情

### 任务详情
el-progress + 阶段 stepper + 自动滚动日志（尾部 200 条窗口 + 暂停/显示全部开关，超长行截断+展开）；完成态绿色 + 下载按钮；失败态原因摘要 + 重跑按钮。

### 关键交互
- 轮询：`setInterval 2s` + `visibilitychange`（hidden 停、visible 补拉）；连续 3 次失败指数退避（2→4→8→16→30s）
- 只轮询"当前查看任务"；提交按钮防重复（disabled+loading，达到并发上限禁用）
- 下载：axios blob → createObjectURL → a[download]
- `done` 语义 = 输出文件已全部落盘（服务端保证写完后才置 done）
- 时间：后端返回 ISO 带偏移，前端 toLocaleString 转本地，不手写 +8
- 全局 axios 拦截器统一错误码→文案映射（2xxx 配置缺失/3xxx 网络/4xxx 引擎）
- 移动端：el-upload 回退点击选择、表格改卡片流、日志默认折叠

---

## 8. 日志与监控

- **两级日志**：系统日志 `data/logs/app.log`（RotatingFileHandler 5MB×5）+ 任务日志（deque + tasks/<id>.log 双写，utf-8）
- **统一格式**：`[时间][级别][task=?] 消息`
- **脱敏**（`sanitize()` 统一入口，日志与 API 响应前必过）：Cookie 正则、XSRF token、15-22 位订单号保留前 6 位
- **指标** → `data/stats.json` 原子落盘 + `GET /api/stats`：任务数/成功率/P95 耗时/API 失败率/缓存命中率
- **排查路径**：任务卡住→任务日志末条+系统 traceback；风控→grep 403|429；Excel 失败→outputs 半成品残留

---

## 9. 测试与验收

### 9.1 引擎一致性（核心验收）
- **黄金样本**：GUI 跑真实数据存档 `tests/golden/`（含输入副本）
- **对比脚本** `compare_workbooks.py`：sheet 名/顺序、合并单元格、列宽(±0.5)、单元格值（严格含类型）、公式（规范化后容忍加数顺序）、样式（fill/border/字体/数字格式）
- 通过标准：公式列外**零容忍差异**

### 9.2 测试清单
- 单测：工具方法（to_float/clean_id/find_header_index/extract_store_name/extract_date_from_filename/parse_cost_date_range）+ 5 个 load_*（构造最小 xlsx fixture）
- API 集成：Flask test_client 全链路 + monkeypatch `get_charge_order_list` 注入假响应
- 冒烟：假 Cookie + 构造 CSV（税运全失败但流程走通、Excel 数值与手算一致）
- Fixture 规格：5 类配置 + 2 份订单 CSV（覆盖日期区间/多天"至"/gbk 与 utf-8/>15 位订单号）
- 手动验收：手机端、多任务并发、大文件、重启容错、24h 清理

### 9.3 DoD 要点
- M1：引擎无 GUI 依赖、与 GUI 逐字节一致、异常全覆盖
- M2：全部 API 可用、2~3 并发、重启恢复、上传校验生效
- M3：手机全流程、空/错误态、日志轮询无丢无重
- M4：黄金样本 100%（公式列容忍顺序差）、覆盖率 ≥80%
- M5：start.bat 一键启动、局域网手机验证、README 完整

**Blocker**：数据不一致、500/串店、校验失效、重启故障、文件损坏、手机不可用。

---

## 10. 风险登记册

| ID | 级别 | 描述 | 缓解 |
|---|---|---|---|
| R1 | **P1** | 真实 Cookie 已入 git 历史（根目录 cookie.txt、tools/query_inventory.py:101） | 立即轮换 Cookie；git rm --cached + .gitignore；本地私库可 filter-repo 清洗；公库必换 Cookie |
| R2 | **P1** | **引擎 bug**：销售计划登记表只统计最后店铺（gui_batch_query.py:1550 残留变量 store_link_map） | Web 版实现时改为 `link_map.get(s_name, {})`，多店铺回归用例 |
| R3 | **P2** | 引擎边界 bug：日期兜底"今天"(755)、SKU 尾数误判数量(1095)、推广日期格式错配致推广费 0(996)、空输入假成功(1789)、多文件表头错位(967) | Web 版输入校验前移（空输入报错、日期解析统一、表头一致性校验）；GUI 版暂不修避免双份漂移 |
| R4 | P2 | 菜鸟 API 风控：多用户并发触发封禁 | 全局限流令牌桶（≤2 QPS）+ 重试 2 次指数退避(1s/2s/4s+jitter) + 连续失败 5 单熔断 10s + 全局 20 次熔断 30s；3xx/401 立即失败不重试 |
| R5 | P2 | 服务版与 GUI 输出差异（API 响应变化/浮点/双份逻辑漂移） | engine.py 单源 + M4 黄金样本兜底 |
| R6 | P2 | 配置表格式与代码假设不符（实测成本表无日期列） | 上传校验（表头契约+魔数）+ 友好报错 + 模板文件 |
| R7 | P2 | openpyxl 私有 API 跨版本（wb._sheets） | 锁 3.1.x + 改 move_sheet |
| R8 | P2 | 业务人员误操作（删文件/重复提交/关窗口） | 快照隔离 + 幂等 + 运行中提示勿关窗口 + bat 启动 |
| R9 | P2 | 部署安全（局域网明文 Cookie、无权限控制） | 简单 token + cookie 权限 600 + 日志脱敏 |
| R10 | P3 | 结果 xlsx 无版本/备份 | 输出带时间戳归档，保留近 N 份 |

**处置优先级**：R1、R2 立即修复；R3 在 Web 版实现时一并修复（记录于引擎移植说明）；R4~R9 开发期处理；R10 排期。

---

## 11. 交付计划（WBS 总计约 68h）

| 里程碑 | 交付物 | 验收 | 工时 |
|---|---|---|---|
| **M1 引擎抽取** | engine.py（ProfitEngine） | 纯 Python 独立运行；与 GUI 同名函数输出一致 | 16h |
| **M2 服务层** | app.py/tasks.py/storage.py：上传→队列→轮询→下载 + SQLite | 2~3 并发、进度可轮询、重启可恢复、结果可下载 | 16h |
| **M3 前端** | index.html（Vue2+Element UI） | 手机端完成上传→发起→进度→下载全流程 | 12h |
| **M4 测试一致性** | 黄金样本 + 对比脚本 + 测试报告 | 同输入下与 GUI 基线一致（公式顺序容忍） | 16h |
| **M5 打磨上线** | start.bat、README、清理策略 | 一键启动、局域网手机验证通过 | 8h |

**依赖**：M2/M3/M4 依赖 M1；M5 依赖 M2~M4。
**并行**：M1 完成纯计算部分后，M2 接口 + M3 前端（假接口联调）并行；M4 样本采集可与 M2/M3 并行（GUI 跑基线）。

### Backlog（先不做）
多账号/多租户、登录权限、定时任务、SSE、拖拽上传、失败明细导出、GUI 下线（条件：Web 稳定 ≥2 月 + 全员转 Web + 双端一致）。

---

## 12. 最终交付清单

`profit_service/`（engine.py、app.py、tasks.py、storage.py、templates/index.html、static/、requirements.txt、start.bat、README.md）+ `tests/`（fixtures、compare_workbooks.py、单测/集成测试）+ `docs/` 本规划文档。
