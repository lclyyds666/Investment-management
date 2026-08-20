# 泉城欧乐堡酒店品牌平台拆分 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将泉城欧乐堡三酒店、两平台的 18 张明细表解析并保存为一期六行，页面按酒店品牌与标准平台组合显示且金额与生产计算公式一致。

**Architecture:** 后端从工作表名称提取酒店品牌和基础平台，按二元键维护独立聚合及逐日快照，并通过现有解析接口返回可选 `hotel_name`。前端优先使用解析品牌，组合显示与稳定排序，但保存时仍分开提交两个字段；历史逐日快照恢复也使用二元键精确匹配。

**Tech Stack:** Python 3、FastAPI、Pydantic、openpyxl、Vue 3、Element Plus、Vitest。

## Global Constraints

- `hotel_name` 仅保存 `海洋`、`骑士`、`长颈鹿`，`platform` 仅保存标准平台 `携程`、`美团`。
- 沿用核销率 90%、每间夜 44 元和逐日四舍五入规则，不修改计算引擎。
- 取消、零值、负数冲销和重复订单调整记录继续逐行累加。
- 无已知酒店品牌的旧文件继续按平台聚合。
- 不迁移或重写历史酒店台账。

---

### Task 1: 后端品牌平台双维解析

**Files:**
- Create: `backend/tests/test_hotel_brand_platform_parser.py`
- Modify: `backend/app/services/hotel_ledger.py:40-410`
- Modify: `backend/app/schemas/hotel_ledger.py:9-31`

**Interfaces:**
- Consumes: `parse_hotel_file(content, filename, scenic_id, rate_hexiao, rate_settle, commission_rate)`。
- Produces: 每个 `platforms[]` 元素新增 `hotel_name: str`，品牌文件按六个二元组输出，普通文件保持平台聚合。

- [ ] **Step 1: 写品牌拆分与旧文件兼容的失败测试**

```python
def test_three_hotel_brands_are_split_into_six_rows(self):
    parsed = parse_hotel_file(self._branded_workbook(), "酒店2026.1.25-2.21.xlsx", **RATES)
    self.assertEqual(
        [(row["hotel_name"], row["platform"]) for row in parsed["platforms"]],
        [("海洋", "携程"), ("海洋", "美团"), ("骑士", "携程"),
         ("骑士", "美团"), ("长颈鹿", "携程"), ("长颈鹿", "美团")],
    )

def test_unbranded_sheets_still_merge_by_platform(self):
    parsed = parse_hotel_file(self._legacy_workbook(), "酒店2026.1.25-1.31.xlsx", **RATES)
    self.assertEqual([(row["hotel_name"], row["platform"]) for row in parsed["platforms"]], [("", "携程")])
```

- [ ] **Step 2: 运行测试并确认现有解析器只返回两行且遗漏长颈鹿**

Run: `$env:PYTHONPATH=(Resolve-Path 'backend').Path; & 'D:\Investment-management\backend\.venv\Scripts\python.exe' -m unittest backend.tests.test_hotel_brand_platform_parser -v`

Expected: FAIL，解析结果缺少 `hotel_name`，且品牌工作表未拆为六组。

- [ ] **Step 3: 实现工作表维度识别和二元聚合**

```python
HOTEL_BRANDS = ("海洋", "骑士", "长颈鹿")
BRANDED_PLATFORM_ORDER = ("携程", "美团", "抖音")

def _hotel_brand_of(title: str) -> str:
    return next((brand for brand in HOTEL_BRANDS if (title or "").startswith(brand)), "")

def _platform_of(title: str) -> str | None:
    brand = _hotel_brand_of(title)
    candidate = (title or "")[len(brand):] if brand else (title or "")
    return next((platform for platform in PLATFORMS
                 if candidate.startswith(platform) or platform in candidate[:4]), None)
```

将 `agg` 的键改为 `(hotel_name, platform)`，每组返回 `hotel_name`，并用品牌顺序及品牌内携程、美团顺序生成响应；非品牌组沿用 `PLATFORMS` 顺序。

- [ ] **Step 4: 给解析响应模型增加酒店名称**

```python
class ParsedPlatform(BaseModel):
    platform: str = ""
    hotel_name: str = ""
```

- [ ] **Step 5: 运行后端相关测试**

Run: `$env:PYTHONPATH=(Resolve-Path 'backend').Path; & 'D:\Investment-management\backend\.venv\Scripts\python.exe' -m unittest backend.tests.test_hotel_brand_platform_parser backend.tests.test_hotel_scenic_config -v`

Expected: PASS。

- [ ] **Step 6: 提交后端解析改造**

```powershell
git add -- backend/app/services/hotel_ledger.py backend/app/schemas/hotel_ledger.py backend/tests/test_hotel_brand_platform_parser.py
git commit -m "feat: split hotel imports by brand and platform"
```

### Task 2: 精确恢复品牌逐日快照

**Files:**
- Modify: `backend/app/api/v1/endpoints/hotel_ledger.py:82-121`
- Modify: `backend/tests/test_hotel_brand_platform_parser.py`

**Interfaces:**
- Consumes: 解析结果中的 `hotel_name`、`platform` 和数据库行的同名字段。
- Produces: `_recover_daily_json(row)` 返回与该酒店品牌和平台同时匹配的 `daily_json`。

- [ ] **Step 1: 写同平台不同品牌恢复失败测试**

```python
def test_daily_recovery_matches_hotel_name_and_platform(self):
    row = SimpleNamespace(
        platform="携程", hotel_name="骑士", daily_json="",
        scenic_id="quancheng-ouleb", detail_stored="source.xlsx",
        detail_name="酒店2026.1.25-2.21.xlsx", source_file="source.xlsx",
        rate_hexiao=Decimal("0.90"), rate_settle=Decimal("0.94"),
        commission_rate=Decimal("0.06"),
    )
    parsed = {"platforms": [
        {"platform": "携程", "hotel_name": "海洋", "daily_json": "ocean"},
        {"platform": "携程", "hotel_name": "骑士", "daily_json": "knight"},
    ]}
    with TemporaryDirectory() as temp_dir:
        Path(temp_dir, "source.xlsx").write_bytes(b"xlsx")
        with patch.object(hotel_endpoint, "_detail_dir", return_value=Path(temp_dir)), \
             patch.object(hotel_endpoint.hl_svc, "parse_hotel_file", return_value=parsed):
            self.assertEqual(hotel_endpoint._recover_daily_json(row), "knight")
```

- [ ] **Step 2: 运行单测确认当前错误选中第一条携程数据**

Run: `$env:PYTHONPATH=(Resolve-Path 'backend').Path; & 'D:\Investment-management\backend\.venv\Scripts\python.exe' -m unittest backend.tests.test_hotel_brand_platform_parser.HotelBrandPlatformParserTest.test_daily_recovery_matches_hotel_name_and_platform -v`

Expected: FAIL，实际返回 `ocean`。

- [ ] **Step 3: 将恢复匹配改为品牌与平台联合条件**

```python
item for item in info.get("platforms", [])
if item.get("platform") == row.platform
and (item.get("hotel_name") or "") == (row.hotel_name or "")
```

- [ ] **Step 4: 运行后端测试并提交**

Run: `$env:PYTHONPATH=(Resolve-Path 'backend').Path; & 'D:\Investment-management\backend\.venv\Scripts\python.exe' -m unittest backend.tests.test_hotel_brand_platform_parser backend.tests.test_ledger_commission_linkage -v`

Expected: PASS。

```powershell
git add -- backend/app/api/v1/endpoints/hotel_ledger.py backend/tests/test_hotel_brand_platform_parser.py
git commit -m "fix: recover branded hotel daily snapshots"
```

### Task 3: 前端品牌映射、组合标签和排序

**Files:**
- Modify: `frontend/src/utils/hotelLedgerDraft.js`
- Modify: `frontend/src/utils/hotelLedgerDraft.test.js`
- Modify: `frontend/src/components/HotelLedger.vue:31-38,82-91,255,342-365`

**Interfaces:**
- Produces: `hotelPlatformLabel(row): string` 和 `compareHotelLedgerRows(left, right): number`。
- Consumes: 后端返回的 `hotel_name`；`createHotelDraftRows` 与保存表格 `displayRows` 使用统一排序。

- [ ] **Step 1: 写品牌优先、标签和排序的失败测试**

```javascript
expect(createHotelDraftRows(branded, '默认酒店').map((row) => row.hotel_name))
  .toEqual(['海洋', '海洋', '骑士', '骑士', '长颈鹿', '长颈鹿'])
expect(hotelPlatformLabel({ hotel_name: '海洋', platform: '携程' })).toBe('海洋携程')
expect([...rows].sort(compareHotelLedgerRows).map(hotelPlatformLabel)).toEqual([
  '海洋携程', '海洋美团', '骑士携程', '骑士美团', '长颈鹿携程', '长颈鹿美团'
])
```

- [ ] **Step 2: 运行测试并确认失败**

Run: `npm test -- --run src/utils/hotelLedgerDraft.test.js`

Expected: FAIL，草稿仍全部使用默认酒店名，标签与排序函数不存在。

- [ ] **Step 3: 实现公用标签和排序函数并接入草稿映射**

```javascript
export function hotelPlatformLabel(row) {
  return `${row?.hotel_name || ''}${row?.platform || ''}` || '—'
}

export function compareHotelLedgerRows(left, right) {
  const hotels = ['海洋', '骑士', '长颈鹿']
  const brandedPlatforms = ['携程', '美团', '抖音']
  const legacyPlatforms = ['抖音', '美团', '携程']
  const leftHotel = hotels.indexOf(left?.hotel_name)
  const rightHotel = hotels.indexOf(right?.hotel_name)
  if (leftHotel >= 0 || rightHotel >= 0) {
    if (leftHotel !== rightHotel) return (leftHotel < 0 ? hotels.length : leftHotel) - (rightHotel < 0 ? hotels.length : rightHotel)
    return brandedPlatforms.indexOf(left?.platform) - brandedPlatforms.indexOf(right?.platform)
  }
  return legacyPlatforms.indexOf(left?.platform) - legacyPlatforms.indexOf(right?.platform)
}

hotel_name: platform.hotel_name || defaultHotelName
```

- [ ] **Step 4: 页面显示组合标签并复用排序函数**

草稿与已保存表格的平台单元格调用 `hotelPlatformLabel(row)`；`displayRows` 的期内行调用 `compareHotelLedgerRows`，保存字段不变。

- [ ] **Step 5: 运行前端测试和构建并提交**

Run: `npm test -- --run src/utils/hotelLedgerDraft.test.js`

Run: `npm run build`

Expected: PASS。

```powershell
git add -- frontend/src/utils/hotelLedgerDraft.js frontend/src/utils/hotelLedgerDraft.test.js frontend/src/components/HotelLedger.vue
git commit -m "feat: display branded hotel platform rows"
```

### Task 4: 真实文件与全量回归验收

**Files:**
- Verify: `C:\Users\dell\Desktop\海洋骑士长颈鹿2026.1.25-2.21.xlsx`
- Verify: `docs/superpowers/specs/2026-08-20-quancheng-hotel-brand-platform-import-design.md`

**Interfaces:**
- Consumes: 最终 `parse_hotel_file` 输出和前端映射函数。
- Produces: 六行真实文件核算记录与通过的相关测试、前端构建。

- [ ] **Step 1: 使用真实文件运行生产解析器**

通过环境变量传递桌面文件路径，调用 `parse_hotel_file(file_bytes, workbook_name, scenic_id="quancheng-ouleb", rate_hexiao=Decimal("0.90"), rate_settle=Decimal("0.94"), commission_rate=Decimal("0.06"))`，打印六行组合、基数、间夜、订单、核销、服务费和结算金额。

- [ ] **Step 2: 逐项核对规格中的六行验收表**

Expected: 六行顺序和所有金额、间夜、订单计数与规格完全一致；总基数为 `1977921.50`，总间夜为 `1353`，总核销为 `1780129.35`，总服务费为 `59532.00`，总结算金额为 `1839661.35`。

- [ ] **Step 3: 运行后端酒店台账回归测试**

Run: `$env:PYTHONPATH=(Resolve-Path 'backend').Path; & 'D:\Investment-management\backend\.venv\Scripts\python.exe' -m unittest discover -s backend/tests -p 'test_hotel*.py' -v`

Expected: PASS。

- [ ] **Step 4: 运行前端完整单元测试与生产构建**

Run: `npm test`

Run: `npm run build`

Expected: PASS。

- [ ] **Step 5: 检查补丁并提交验收调整**

Run: `git diff --check`

如验收引出必要的测试或小幅修正，仅提交本功能相关文件；若无修正则不创建空提交。
