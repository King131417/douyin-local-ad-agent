# 巨量引擎本地推（Local Push）Open API 完整接口审查报告

> 审查日期：2026-07-03
> 数据来源：Go SDK v1.34.1 (`bububa/oceanengine`) + 官方开放平台文档
> 项目路径：`douyin-local-ad-agent/src/api/client.py`

---

## 一、官方 API 接口全景（共 5 大模块，26 个接口）

基于 Go SDK v1.34.1 的 `marketing-api/LOCAL.md` 和 `marketing-api/api/local/` 目录结构：

### 1.1 数据报表模块 `local/report` — 4 个接口

| # | 接口 | Endpoint | 说明 |
|---|------|----------|------|
| 1 | AccountGet | `GET /v3.0/local/report/account/get/` | 查询账户维度数据 |
| 2 | ProjectGet | `GET /v3.0/local/report/project/get/` | 获取项目维度数据 |
| 3 | PromotionGet | `GET /v3.0/local/report/promotion/get/` | 获取广告（投放单元）维度数据 |
| 4 | MaterialGet | `GET /v3.0/local/report/material/get/` | 获取素材维度数据 |

**结论：本地推报表只有这 4 个维度接口，没有 Custom Report（自定义报表）。** 对比普通巨量引擎广告的 Custom Report，本地推不支持自定义维度和指标的灵活组合。

### 1.2 项目管理模块 `local/project` — 9 个接口

| # | 接口 | Endpoint | 说明 |
|---|------|----------|------|
| 5 | Create | `POST /v3.0/local/project/create/` | 创建项目 |
| 6 | Update | `POST /v3.0/local/project/update/` | 更新项目 |
| 7 | List | `GET /v3.0/local/project/list/` | 获取项目列表 |
| 8 | Detail | `GET /v3.0/local/project/detail/` | 获取项目详情 |
| 9 | StatusUpdate | `POST /v3.0/local/project/status/update/` | 批量更新项目状态 |
| 10 | ProductGet | `GET /v3.0/local/project/product/get/` | 获取可投商品列表 |
| 11 | AwemeAuthorizedGet | `GET /v3.0/local/project/aweme/authorized/get/` | 获取本地推创编可用抖音号 |
| 12 | CustomAudienceGet | `GET /v3.0/local/project/custom_audience/get/` | 查询本地推创编可用人群包 |
| 13 | MultiPoiIDsGet | `GET /v3.0/local/project/poi/multi_poi_ids/get/` | 根据多门店ID拉取门店ID |

### 1.3 广告管理模块 `local/promotion` — 6 个接口

| # | 接口 | Endpoint | 说明 |
|---|------|----------|------|
| 14 | Create | `POST /v3.0/local/promotion/create/` | 创建广告 |
| 15 | Update | `POST /v3.0/local/promotion/update/` | 更新广告 |
| 16 | List | `GET /v3.0/local/promotion/list/` | 获取广告列表 |
| 17 | Detail | `GET /v3.0/local/promotion/detail/` | 获取广告详情 |
| 18 | StatusUpdate | `POST /v3.0/local/promotion/status/update/` | 批量更新广告状态 |
| 19 | ProductGetByPoiIDs | `GET /v3.0/local/promotion/product/get_by_poi_ids/` | 根据门店ID查询门店下商品ID |

### 1.4 素材管理模块 `local/file` — 5 个接口

| # | 接口 | Endpoint | 说明 |
|---|------|----------|------|
| 20 | UploadTaskCreate | `POST /v3.0/local/file/upload_task/create/` | 异步上传本地推视频 |
| 21 | VideoUploadTaskList | `GET /v3.0/local/file/video_upload_task/list/` | 查询异步上传本地推视频结果 |
| 22 | VideoUpload | `POST /v3.0/local/file/video/upload/` | 上传视频 |
| 23 | VideoGet | `GET /v3.0/local/file/video/get/` | 获取素材库视频 |
| 24 | VideoAwemeGet | `GET /v3.0/local/file/video/aweme/get/` | 获取抖音主页视频 |

### 1.5 线索管理模块 `local/clue` — 2 个接口

| # | 接口 | Endpoint | 说明 |
|---|------|----------|------|
| 25 | LifeGet | `GET /v2/tools/clue/life/get/` | 获取本地推线索列表 |
| 26 | LifeCallback | `POST /v2/tools/clue/life/callback/` | 本地推线索回传 |

---

## 二、当前 `client.py` 已实现方法清单

| # | 方法名 | 对应官方接口 | 状态 |
|---|--------|------------|------|
| 1 | `discover_valid_accounts()` | 本地封装（调用 account report 探活） | ✅ |
| 2 | `fetch_all_account_names()` | v2 advertiser/fund/get/ | ✅ |
| 3 | `get_account_report()` | `GET /v3.0/local/report/account/get/` | ✅ |
| 4 | `get_account_report_date_range()` | 同上（日期批处理包装） | ✅ |
| 5 | `get_promotion_report()` | `GET /v3.0/local/report/promotion/get/` | ✅ |
| 6 | `get_material_report()` | `GET /v3.0/local/report/material/get/` | ✅ |
| 7 | `sync_all_materials()` | 同上（多账户批处理） | ✅ |
| 8 | `sync_all_accounts()` | account report 多账户批处理 | ✅ |
| 9 | `get_promotion_list()` | `GET /v3.0/local/promotion/list/` | ✅ |
| 10 | `get_project_list()` | `GET /v3.0/local/project/list/` | ✅ |
| 11 | `get_project_report()` | `GET /v3.0/local/report/project/get/` | ✅ |
| 12 | `reconcile_deleted_entities()` | 本地封装（对账逻辑） | ✅ |
| 13 | `get_clue_data()` | `GET /v2/tools/clue/life/get/` | ✅ |

**汇总：已实现 13 个方法，覆盖 10 个独立 API 端点。所有 4 个报表接口均已实现。**

---

## 三、未使用但可能有价值的接口

### 3.1 高价值（建议优先评估）

| 接口 | 价值说明 |
|------|---------|
| **Project Detail** (`/local/project/detail/`) | 获取项目完整信息（预算、出价、定向、状态等），对投流分析 Agent 理解投放策略极有价值 |
| **Promotion Detail** (`/local/promotion/detail/`) | 获取投放单元完整信息（预算、出价、定向、学习期状态等），可用于深度分析 |
| **Product Get** (`/local/project/product/get/`) | 获取可投商品列表，关联商品维度的投放分析 |
| **Product GetByPoiIDs** (`/local/promotion/product/get_by_poi_ids/`) | 获取门店关联商品，用于门店-商品关联分析 |

### 3.2 中等价值

| 接口 | 价值说明 |
|------|---------|
| **Aweme Authorized Get** | 获取可用抖音号列表，可用于账号维度分析 |
| **Multi PoiIDs Get** | 门店ID查询，用于门店维度数据分析 |
| **Video Get** | 获取素材库视频详情，用于素材质量分析 |
| **Video Aweme Get** | 获取抖音主页视频，用于素材来源分析 |

### 3.3 低价值（分析场景不常用）

| 接口 | 原因 |
|------|------|
| Project/Promotion Create/Update | 投放管理操作，投流分析 Agent 通常不需要创建/修改 |
| Status Update | 同上 |
| Custom Audience Get | 人群包查询，分析场景少用 |
| File Upload 系列 | 素材上传，分析场景不需要 |
| Life Callback | 线索回传，分析场景不需要 |

---

## 四、参数与配置差异深度分析

### 4.1 `time_granularity` — 时间粒度参数（**我们未使用**）

官方 SDK 所有报表接口都支持 `time_granularity` 参数：

| 枚举值 | 说明 | 时间范围限制 |
|--------|------|-------------|
| `TIME_GRANULARITY_DAILY` | 按天维度（默认值） | 不超过 365 天 |
| `TIME_GRANULARITY_HOURLY` | 按小时维度 | 不超过 7 天 |
| `TIME_GRANULARITY_TOTAL` | 汇总 | 不超过 365 天 |

**当前情况：** 我们的代码完全不传 `time_granularity`，API 默认返回按天数据（DAILY）。

**影响评估：**
- 如果我们需要小时级数据用于实时分析，需要新增此参数
- 如果我们需要汇总值做效率优化（减少分页），可使用 TOTAL 模式
- **当前行为与默认值一致，无需紧急修改**

### 4.2 `order_type` / `order_field` — 排序参数（**我们未使用**）

官方支持 `order_type`（ASC/DESC，默认 DESC）和 `order_field`（按任意指标排序）。

**当前情况：** 我们通过自动分页遍历全量数据，所以排序对最终结果无影响。

**潜在问题：** 如果我们后续使用 TOTAL 模式只需一页数据，排序才有意义。当前无影响。

### 4.3 `page_size` — 分页参数差异

| 参数 | 我们的值 | SDK 允许值 | 默认值 |
|------|---------|-----------|--------|
| account report | 50 | 10, 20, 50, **100** | 10 |
| promotion report | 50 | 10, 20, 50, **100** | 10 |
| material report | 50 (min 10) | 10, 20, 50, **100** | 10 |
| project report | 50 | 10, 20, 50, **100** | 10 |

**风险：** 我们使用 50 而非最大值 100，在数据量大时会导致更多 API 调用次数。虽然结果完整，但效率可优化。

**建议：** 将 page_size 默认值改为 100，减少 API 调用次数。

### 4.4 `campaign_type` 参数 — 通投/搜索过滤（**API 文档与实现不一致的 Bug**）

这是最重要的发现：

- **SDK 结构：** `campaign_type` 位于 `Filtering` 对象内（所有报表接口一致）
- **我们的代码：** 最初按部分文档放在顶层，实测发现被忽略，已修复为放在 `filtering` 内
- **当前实现（`get_account_report` 第 326-329 行）：** 已将 `campaign_type` 正确放在 `filtering` JSON 内

```python
# ✅ 当前正确实现
if campaign_type:
    params["filtering"] = json.dumps({"campaign_type": campaign_type})
```

**注意：** `get_promotion_report()` 和 `get_project_report()` 目前没有 `campaign_type` 过滤参数！如果需要分别分析通投和搜索的数据，需要给这两个方法也加上。

### 4.5 Filtering 完整参数对比 — **我们有重大遗漏**

官方 SDK 支持的 filtering 字段非常丰富，我们只用了极小一部分：

| Filtering 字段 | Account | Project | Promotion | Material | 我们用了？ |
|---------------|---------|---------|-----------|----------|-----------|
| campaign_type | ✅ | ✅ | ✅ | ✅ | ✅ (仅 account) |
| marketing_goal | ✅ | ✅ | ✅ | ❌ | ❌ |
| local_delivery_scene | ✅ | ✅ | ✅ | ✅ | ❌ |
| external_action | ✅ | ✅ | ✅ | ✅ | ❌ |
| delivery_mode | ✅ | ✅ | ✅ | ✅ | ❌ |
| promotion_ids | ❌ | ❌ | ✅ | ✅ | ✅ (仅 material) |
| material_ids | ❌ | ❌ | ❌ | ✅ | ❌ |
| material_type | ❌ | ❌ | ❌ | ✅ | ❌ |
| project_ids (cdp_project_ids) | ❌ | ✅ | ❌ | ❌ | ❌ |

**这意味着我们无法按以下维度做细分分析：**
- 营销场景（直播 vs 短视频/图文）
- 推广目的（线索 vs 内容加热 vs 门店引流 vs 团购成交）
- 优化目标（多种转化目标）
- 投放模式（自动投放 vs 手动投放）

**建议：** 在 `get_account_report()` 中添加 `marketing_goal` 和 `local_delivery_scene` 过滤参数。

---

## 五、Metrics 字段完整清单与对比

### 5.1 基础消耗与展示指标

| JSON 字段 | 中文名称 | 我们用了？ | 备注 |
|-----------|---------|-----------|------|
| `stat_cost` | 消耗(元) | ✅ | — |
| `show_cnt` | 展示次数 | ✅ | — |
| `click_cnt` | 点击次数 | ✅ | — |
| `ctr` | 点击率 | ✅ | — |
| `cpc_platform` | 点击均价(元) | ✅ | — |
| `cpm_platform` | 平均千次展示费用(元) | ✅ | — |

### 5.2 行为时间转化指标

| JSON 字段 | 中文名称 | 我们用了？ | 备注 |
|-----------|---------|-----------|------|
| `convert_cnt` | 转化数 | ✅ | — |
| `conversion_rate` | 转化率 | ✅ | — |
| `conversion_cost` | 转化成本 | ✅ | — |
| `message_action_cnt` | 私信咨询数 | ✅ | — |
| `clue_message_count` | 私信留资数 | ✅ | — |
| `phone_confirm_cnt` | 电话拨打数 | ✅ | — |
| `phone_connect_cnt` | 电话接通数 | ✅ | — |
| `clue_pay_order_cnt` | 团购线索数 | ✅ | — |
| `form_cnt` | 表单提交数 | ✅ | — |
| `intention_form_cnt` | 意向表单数 | ❌ | **新增** |
| `intention_phone_cnt` | 意向话单数 | ❌ | **新增** |
| `intention_message_clue_cnt` | 意向咨询数 | ❌ | **新增** |

### 5.3 计费时间归因指标

| JSON 字段 | 中文名称 | 我们用了？ | 备注 |
|-----------|---------|-----------|------|
| `attribution_convert_cnt` | 转化数(计费时间) | ✅ | — |
| `attribution_conversion_rate` | 转化率(计费时间) | ❌ | **遗漏** |
| `attribution_conversion_cost` | 转化成本(计费时间) | ❌ | **遗漏** |
| `attribution_message_action_cnt` | 私信咨询数(计费时间) | ✅ | — |
| `attribute_clue_message_count` | 私信留资数(计费时间) | ❌ | **账户级实测不支持** |
| `attribution_clue_pay_order_cnt` | 团购线索数(计费时间) | ❌ | **新增** |
| `attribution_form_cnt` | 表单提交数(计费时间) | ❌ | **新增** |
| `attribution_phone_confirm_cnt` | 电话拨打数(计费时间) | ❌ | **新增** |
| `attribute_phone_connect_cnt` | 电话接通数(计费时间) | ❌ | **新增** |
| `attribution_intention_form_cnt` | 意向表单数(计费时间) | ❌ | **新增** |
| `attribution_intention_phone_cnt` | 意向话单数(计费时间) | ❌ | **新增** |
| `attribution_intention_message_clue_cnt` | 意向咨询数(计费时间) | ❌ | **新增** |

> ⚠️ 注意：SDK 中有些字段使用 `attribute_` 前缀而非 `attribution_`（官方 SDK 的 typo，但 API 实际接受的 key 需要以实测为准）

### 5.4 视频与互动指标（`LOCAL_VIDEO_METRICS`）

| JSON 字段 | 中文名称 | 我们用了？ | 备注 |
|-----------|---------|-----------|------|
| `total_play` | 视频播放次数 | ✅ | — |
| `play_duration_3s` | 视频3s播放 | ✅ | — |
| `play_duration_5s` | 视频5s播放 | ❌ | **遗漏** |
| `play_duration_5s_show_cnt_rate` | 视频5s播放率 | ❌ | **遗漏** |
| `play_25_feed_break` | 25%进度播放 | ❌ | **遗漏** |
| `play_50_feed_break` | 50%进度播放 | ❌ | **遗漏** |
| `play_75_feed_break` | 75%进度播放 | ❌ | **遗漏** |
| `play_over` | 完播次数 | ✅ | — |
| `play_over_rate` | 完播率 | ✅ | — |
| `dy_like` | 点赞 | ✅ | — |
| `dy_like_rate` | 点赞率 | ❌ | **遗漏** |
| `dy_comment` | 评论 | ✅ | — |
| `dy_share` | 分享 | ✅ | — |
| `dy_collect` | 收藏 | ✅ | — |
| `dy_follow` | 新增粉丝 | ✅ | — |
| `dy_home_visited` | 主页访问 | ✅（自定义列表） | ⚠️ SDK Report 结构体中没有此字段 |
| `poi_recommend_count` | 浏览商户人数 | ✅（自定义列表） | ⚠️ SDK Report 结构体中没有此字段 |

### 5.5 直播指标（**完全遗漏**）

| JSON 字段 | 中文名称 | 我们用了？ |
|-----------|---------|-----------|
| `luban_live_enter_cnt` | 直播间观看次数 | ❌ |
| `live_watch_one_minute_count` | 直播间超1分钟停留 | ❌ |
| `luban_live_comment_cnt` | 直播间评论次数 | ❌ |
| `luban_live_share_cnt` | 直播间分享次数 | ❌ |

**⚠️ 关键发现：** 如果客户投放的是直播推广，我们的 metrics 列表完全缺失直播核心指标，会导致直播场景的分析数据不完整。

### 5.6 `dy_home_visited` 和 `poi_recommend_count` 的特殊说明

这两个字段出现在我们的 `LOCAL_VIDEO_METRICS` 列表中，但 Go SDK v1.34.1 的 `Report` 结构体中**没有**这两个字段。有两种可能：
1. 它们是较新版本 API 新增的字段，SDK 还未更新
2. 它们是无效字段，API 会忽略

**建议：** 实测验证这两个字段是否能返回数据。

---

## 六、分页问题分析

### 6.1 当前分页逻辑

| 方法 | 分页策略 | 终止条件 |
|------|---------|---------|
| `get_account_report` | while True 逐页累加 | `len(rows) == 0` 或 `len(rows) < page_size` |
| `get_promotion_report` | 同上 | 同上 |
| `get_project_report` | 同上 | 同上 |
| `get_material_report` | 同上，额外有 page_info 检查 | `page > page_info.total_page` 或 rows 为空 |
| `get_promotion_list` | 同上 | `len(rows) < page_size` |
| `get_project_list` | 同上 | 同上 |
| `get_clue_data` | while True 逐页累加 | `page >= page_info.page_total` |

### 6.2 潜在风险

**风险 1：第一页报错即抛异常**
```python
if result.get("code") != 0:
    if page == 1:
        raise RuntimeError(...)  # 直接中断
```
如果某账户的第一页数据因临时原因失败（如限流），整个批次会被中断。缺少重试机制。

**风险 2：非第一页错误静默丢弃**
如果 page > 1 时遇到错误，代码 break 退出循环，已获取的前几页数据会被返回但不完整。这可能导致数据遗漏且无告警。

```python
if result.get("code") != 0:
    if page == 1:
        raise RuntimeError(...)
    break  # ⚠️ 静默丢弃后续数据
```

**风险 3：material report 的 code=40000 处理**
Material report 特殊处理了 code=40000（无素材数据），但其他接口没有。如果其他接口也返回 40000，会被当作错误处理（但只有 page==1 才抛异常）。

**风险 4：API 默认 page_size=10**
所有报表接口的默认 page_size 是 10，我们设置为 50。如果 page_size 参数传错格式被 API 忽略，会回退到默认 10，导致数据翻 5 倍调用。建议改为 100。

### 6.3 数据遗漏可能性评估

| 场景 | 可能性 | 影响 |
|------|--------|------|
| pageSize 自动回退默认值 | 低 | 多调用 API，数据仍完整 |
| 中间页错误静默丢弃 | 中 | **可能遗漏数据** |
| API 返回空 rows 但实际还有下一页 | 低 | 可能遗漏数据 |
| 账户级数据超过 365 天范围 | 取决于调用方 | 需检查 date_range 方法的分批逻辑 |

---

## 七、数据归因相关参数

### 7.1 行为时间 vs 计费时间

巨量引擎本地推的数据报表支持两种归因口径：

| 口径 | 字段前缀 | 含义 | 与后台 UI 对齐 |
|------|---------|------|---------------|
| 行为时间 | 无前缀（如 `convert_cnt`） | 用户行为实际发生的日期 | ❌ |
| 计费时间 | `attribution_`（如 `attribution_convert_cnt`） | 广告消耗归因的日期 | ✅ |

**我们的代码已经意识到这个差异**（第 28-29 行注释），但 metrics 列表中缺少大量计费时间指标（见 5.3 节）。

**特别注意：** SDK 中部分计费时间字段使用了不一致的前缀：
- `attribution_convert_cnt` — 使用 `attribution_`
- `attribute_clue_message_count` — 使用 `attribute_`（少了个 `n`）
- `attribute_messaction_action_cnt` — 又一种拼写

这些 SDK 内部的拼写不一定影响 API 实际接受的 key，需要实测确认正确的字段名。

### 7.2 归因窗口参数

**重要发现：** 巨量本地推报表 API **没有暴露归因窗口配置参数**（如 attribution_window）。这意味着：
- 归因窗口由巨量引擎后台固定配置，无法通过 API 调整
- 如果需要不同的归因窗口来对比数据，只能切换到巨量引擎广告升级版（非本地推）

---

## 八、项目维度与推广维度数据 Key 不一致问题

| 接口 | 返回数据的 key | 代码中的 key |
|------|--------------|-------------|
| account report | `data_list` | ✅ `data_list` |
| promotion report | `promotion_list` | ✅ `promotion_list` |
| project report | `project_list` | ✅ `project_list` |
| material report | `material_list` | ✅ `material_list` |

✅ 所有 key 匹配正确，无问题。

---

## 九、API v2 vs v3 混合使用

| 调用 | 使用版本 | 状态 |
|------|---------|------|
| 获取账户名称 | v2 `/2/advertiser/fund/get/` | ✅ 本地推无 v3 账户信息接口 |
| 线索列表 | v2 `/2/tools/clue/life/get/` | ✅ 官方指定使用 v2 |
| 所有报表 | v3.0 `/v3.0/local/report/*/` | ✅ 正确 |
| 列表接口 | v3.0 `/v3.0/local/*/list/` | ✅ 正确 |

---

## 十、改进建议优先级排序

### P0 — 必须修复（影响数据准确性）

1. **修正 `dy_home_visited` 和 `poi_recommend_count`** — SDK 中不存在这两个字段，需实测验证是否有效，无效则删除
2. **添加缺失的 core metrics** — 补全 `attribution_conversion_rate`、`attribution_conversion_cost` 等核心计费时间指标
3. **为 promotion 和 project report 添加 `campaign_type` 过滤** — 当前只有 account report 支持

### P1 — 强烈建议（完善分析维度）

4. **添加 `time_granularity` 参数支持** — 支持 TOTAL（汇总）和 HOURLY（小时级）
5. **添加直播指标** — `luban_live_enter_cnt`、`live_watch_one_minute_count` 等
6. **添加 filtering 维度** — `marketing_goal`、`local_delivery_scene`、`delivery_mode`
7. **page_size 改为 100** — 减少 API 调用次数

### P2 — 建议（完善功能）

8. **添加分页错误告警机制** — 防止静默数据丢失
9. **添加 API 调用重试机制** — 处理临时限流
10. **补全意向相关指标** — `intention_form_cnt` 等
11. **补全播放进度指标** — `play_25_feed_break` 等

### P3 — 可考虑（扩展分析能力）

12. **实现 Project Detail** — 获取项目配置信息
13. **实现 Promotion Detail** — 获取广告配置信息
14. **实现 Product Get** — 商品维度分析
15. **实现 Aweme Authorized Get** — 账号维度分析

---

## 十一、完整 Metrics 推荐清单

以下是建议在生产环境中使用的完整 metrics 列表（涵盖所有场景）：

```python
LOCAL_FULL_METRICS = [
    # 基础消耗与展示
    "stat_cost", "show_cnt", "click_cnt", "ctr",
    "cpc_platform", "cpm_platform",

    # 行为时间-转化
    "convert_cnt", "conversion_rate", "conversion_cost",

    # 行为时间-线索
    "message_action_cnt",   # 私信咨询
    "clue_message_count",   # 私信留资
    "phone_confirm_cnt",    # 电话拨打
    "phone_connect_cnt",    # 电话接通
    "clue_pay_order_cnt",   # 团购线索
    "form_cnt",             # 表单提交
    "intention_form_cnt",   # 意向表单（新增）
    "intention_phone_cnt",  # 意向前端（新增）
    "intention_message_clue_cnt",  # 意向咨询（新增）

    # 计费时间-转化（与后台UI对齐）
    "attribution_convert_cnt",
    "attribution_conversion_rate",        # ⚠️ 缺失
    "attribution_conversion_cost",        # ⚠️ 缺失

    # 计费时间-线索
    "attribution_message_action_cnt",
    "attribution_form_cnt",               # ⚠️ 缺失
    "attribution_clue_pay_order_cnt",     # ⚠️ 缺失
    "attribution_phone_confirm_cnt",      # ⚠️ 缺失
    "attribution_intention_form_cnt",     # ⚠️ 缺失
    "attribution_intention_phone_cnt",    # ⚠️ 缺失
    "attribution_intention_message_clue_cnt",  # ⚠️ 缺失

    # 视频互动
    "total_play", "play_duration_3s",
    "play_duration_5s",                   # ⚠️ 缺失
    "play_duration_5s_show_cnt_rate",     # ⚠️ 缺失
    "play_25_feed_break",                 # ⚠️ 缺失
    "play_50_feed_break",                 # ⚠️ 缺失
    "play_75_feed_break",                 # ⚠️ 缺失
    "play_over", "play_over_rate",
    "dy_like", "dy_like_rate",            # dy_like_rate ⚠️ 缺失
    "dy_comment", "dy_share",
    "dy_collect", "dy_follow",

    # 直播（完全缺失）
    "luban_live_enter_cnt",               # ⚠️ 缺失
    "live_watch_one_minute_count",        # ⚠️ 缺失
    "luban_live_comment_cnt",             # ⚠️ 缺失
    "luban_live_share_cnt",               # ⚠️ 缺失
]
```

> ⚠️ `attribution_clue_message_count` 和 `attribution_phone_connect_cnt` 在 SDK 中前缀为 `attribute_`（不带 n），建议根据 API 实测确认正确的字段名后再加入列表。

---

*报告结束。基于 Go SDK v1.34.1 (bububa/oceanengine) 和项目 `douyin-local-ad-agent/src/api/client.py` 生成。*
