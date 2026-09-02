# 合同 AI 证据审查实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为合同 AI 审查增加本地知识片段检索、事实主张核验、可信证据回填和前端可追溯展示。

**Architecture:** `contract_review.py` 保留入口和兼容输出；`contract_evidence.py` 负责知识库分段、词法检索和确定性发现；`contract_review_llm.py` 负责 DeepSeek JSON 调用与服务端证据校验。接口先完成确定性核验，再把检索证据交给模型，最终由服务端生成 Markdown 和统计信息。

**Tech Stack:** FastAPI、SQLAlchemy、Pydantic、OpenAI 兼容 DeepSeek、Vue 3、Element Plus、Vitest、pytest。

## Global Constraints

- 不新增向量数据库、嵌入服务或第三方检索服务。
- 不修改 `biz_knowledge_doc` 表结构，保持现有上传/列表/删除/下载接口兼容。
- DeepSeek 失败、未配置或返回非法 JSON 时接口不返回 500，确定性核验仍必须返回。
- 任何证据只能来自本次服务端召回片段；模型不得自行生成法规原文或引用未返回的片段。
- 保留响应字段 `markdown`、`engine`、`has_attachment`、`kb_used`。
- 不修改审批单校对、客户尽调、经营诊断和通用 AI 助手行为。

---

### Task 1: Build evidence chunking and retrieval

**Files:**
- Create: `backend/app/services/contract_evidence.py`
- Create: `backend/tests/test_contract_evidence.py`

**Interfaces:**
- Produces `EvidenceChunk` with `chunk_id`, `doc_id`, `title`, `category`, `section`, `ordinal`, `text`.
- Produces `retrieve_evidence(db, contract_text, limit=12, max_chars=12000) -> list[EvidenceChunk]`.
- Produces `deterministic_findings(contract_text, structured_fields, evidence) -> list[dict]`.

- [ ] **Step 1: Write failing retrieval tests**

```python
def test_retrieves_later_relevant_document_not_only_first_document():
    docs = [KnowledgeDoc(id=1, title="公司法", category="法律规范", content="无关内容 " * 500),
            KnowledgeDoc(id=2, title="招标投标法", category="法律规范", content="依法必须招标的项目不得拆分规避招标。")]
    chunks = retrieve_evidence(FakeDb(docs), "本合同项目依法必须招标，不得拆分规避招标")
    assert any(chunk.title == "招标投标法" for chunk in chunks)

def test_detects_invalid_percentage_and_missing_cited_law():
    findings = deterministic_findings(
        "违约金按合同金额的120%计算。依据《不存在的管理办法》第三条。",
        {"amount": "100000"},
        [],
    )
    assert {item["code"] for item in findings} >= {"invalid_percentage", "citation_not_found"}
```

- [ ] **Step 2: Run tests to verify failure**

Run: `python -m pytest tests/test_contract_evidence.py -q`
Expected: FAIL because the evidence service and retrieval interfaces do not exist.

- [ ] **Step 3: Implement chunking, lexical scoring, and deterministic findings**

Implement paragraph/条款-aware splitting, normalized Chinese token extraction, title/section/risk-topic/number scoring, per-document deduplication, 12-chunk and 12000-character caps. Implement findings for percentage bounds, explicit law citations absent from evidence, structured amount/party/contract-number mismatches, and conflicting repeated dates/amounts.

- [ ] **Step 4: Run focused tests**

Run: `python -m pytest tests/test_contract_evidence.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/contract_evidence.py backend/tests/test_contract_evidence.py
git commit -m "feat: retrieve contract review evidence locally"
```

### Task 2: Add structured DeepSeek review and evidence validation

**Files:**
- Create: `backend/app/services/contract_review_llm.py`
- Modify: `backend/app/services/contract_review.py:20-125`
- Create: `backend/tests/test_contract_review_llm.py`

**Interfaces:**
- Consumes `EvidenceChunk` and deterministic findings from Task 1.
- Produces `review_with_evidence(contract_text, structured_fields, evidence, findings) -> dict` with `fact_checks`, `risk_findings`, `coverage`, `engine`, `fallback_reason`.

- [ ] **Step 1: Write failing model and validation tests**

```python
def test_invalid_model_evidence_id_becomes_not_found(monkeypatch):
    response = fake_json_response({"fact_checks": [{"claim": "依据公司法", "verdict": "supported", "evidence_ids": ["999:1"]}]})
    monkeypatch.setattr(OpenAI, "chat", FakeChat(response))
    result = review_with_evidence("依据公司法。", {}, [EvidenceChunk("1:1", 1, "公司法", "法律规范", "第一条", 0, "公司法第一条")], [])
    assert result["fact_checks"][0]["verdict"] == "not_found"
    assert result["fact_checks"][0]["evidence"] == []

def test_deepseek_failure_preserves_deterministic_findings(monkeypatch):
    monkeypatch.setattr(OpenAI, "chat", raising_timeout)
    result = review_with_evidence("违约金120%", {}, [], [{"code": "invalid_percentage"}])
    assert result["engine"] == "rule"
    assert result["fallback_reason"] == "provider_error"
    assert result["fact_checks"][0]["code"] == "invalid_percentage"
```

- [ ] **Step 2: Run tests to verify failure**

Run: `python -m pytest tests/test_contract_review_llm.py -q`
Expected: FAIL because structured review and validation do not exist.

- [ ] **Step 3: Implement strict JSON prompt and server-side validation**

Require DeepSeek to return claims, verdicts, evidence IDs, risk findings, and suggestions. Validate enums, discard unknown evidence IDs, backfill evidence text from server chunks, force empty-evidence claims to `not_found`, merge deterministic findings, and calculate claim/support/contradiction/not-found counts plus evidence rate.

- [ ] **Step 4: Update compatibility Markdown generation**

Generate Markdown on the server from validated `fact_checks` and `risk_findings`, include exact evidence quotes and fallback notice, and keep the existing two-section headings so copy/history consumers remain readable.

- [ ] **Step 5: Run focused tests**

Run: `python -m pytest tests/test_contract_review_llm.py tests/test_contract_evidence.py -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/contract_review_llm.py backend/app/services/contract_review.py backend/tests/test_contract_review_llm.py
git commit -m "feat: validate contract AI evidence"
```

### Task 3: Integrate contract endpoint and response metadata

**Files:**
- Modify: `backend/app/api/v1/endpoints/contract.py:687-735`
- Modify: `backend/tests/test_company_permissions.py` or create `backend/tests/test_contract_review_api.py`
- Modify: `frontend/src/api/contract.js:86-89`

**Interfaces:**
- Endpoint continues `POST /api/v1/contracts/{contract_id}/ai-review`.
- Response adds `fact_checks`, `risk_findings`, `retrieved_sources`, `coverage`, `fallback_reason`; old fields remain unchanged.

- [ ] **Step 1: Write failing endpoint tests**

```python
def test_ai_review_returns_retrieved_sources_and_coverage(client, contract, user):
    response = client.post(f"/api/v1/contracts/{contract.id}/ai-review")
    assert response.status_code == 200
    body = response.json()["data"]
    assert {"fact_checks", "risk_findings", "retrieved_sources", "coverage", "fallback_reason"} <= body.keys()
    assert body["retrieved_sources"][0]["chunk_id"]
```

- [ ] **Step 2: Run test to verify failure**

Run: `python -m pytest tests/test_contract_review_api.py -q` or the focused existing endpoint test.
Expected: FAIL because the endpoint only returns Markdown, engine, attachment metadata, and titles.

- [ ] **Step 3: Integrate retrieval, deterministic checks, and structured review**

Pass structured contract fields plus extracted text to the new service, use `retrieved_sources` for `kb_used`, and return non-sensitive fallback reason values (`provider_error`, `invalid_response`, `not_configured`, `no_text`).

- [ ] **Step 4: Run backend focused and full tests**

Run: `python -m pytest tests/test_contract_review_api.py tests/test_contract_evidence.py tests/test_contract_review_llm.py -q` then `python -m pytest tests -q`.
Expected: focused tests pass; full suite remains green except pre-existing fixture skips.

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/v1/endpoints/contract.py backend/tests/test_contract_review_api.py frontend/src/api/contract.js
git commit -m "feat: expose contract review evidence metadata"
```

### Task 4: Display evidence and fact-check results in contract UI

**Files:**
- Modify: `frontend/src/views/contract/index.vue:295-318,760-785`
- Modify: `frontend/src/views/contract/index.test.js:360-390`

**Interfaces:**
- Consumes new endpoint fields from Task 3.
- Displays contradiction, not-found, supported states and expandable evidence without removing current Markdown output.

- [ ] **Step 1: Write failing UI tests**

```javascript
it('renders contradiction, not-found and evidence metadata', async () => {
  const wrapper = mountView()
  wrapper.vm.aiResult = {
    markdown: '审查', engine: 'deepseek', has_attachment: true,
    fact_checks: [
      { claim: '违约金120%', verdict: 'contradicted', risk_level: 'high', reason: '超过允许范围', suggestion: '修改', evidence: [{ title: '公司法', section: '第一条', text: '原文证据' }] },
      { claim: '依据某办法', verdict: 'not_found', risk_level: 'medium', reason: '知识库未找到依据', suggestion: '补充依据', evidence: [] }
    ], coverage: { claim_count: 2, evidence_rate: 0.5 }, fallback_reason: null
  }
  await wrapper.vm.$nextTick()
  expect(wrapper.text()).toContain('存在矛盾')
  expect(wrapper.text()).toContain('知识库未找到依据')
  expect(wrapper.text()).toContain('原文证据')
})
```

- [ ] **Step 2: Run test to verify failure**

Run: `npm test -- --run src/views/contract/index.test.js`
Expected: FAIL because the dialog has no fact-check or evidence section.

- [ ] **Step 3: Implement compact evidence UI**

Add summary tags for evidence rate and fallback reason, a fact-check table/cards with color-coded verdicts, and expandable evidence quotes. Keep the current Markdown block and copy button intact.

- [ ] **Step 4: Run focused and full frontend tests**

Run: `npm test -- --run src/views/contract/index.test.js` then `npm test -- --run`.
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/views/contract/index.vue frontend/src/views/contract/index.test.js
git commit -m "feat: show contract review evidence in UI"
```

### Task 5: Validate, document, and prepare release

**Files:**
- Modify: `backend/README.md` or `docs/superpowers/specs/2026-09-01-contract-ai-evidence-review-design.md` only if implementation behavior needs clarification.
- Test: `backend/tests/test_contract_evidence.py`, `backend/tests/test_contract_review_llm.py`, endpoint/UI tests.

- [ ] **Step 1: Run backend full suite with required fixtures**

Run from `backend`: `python -m pytest tests -q` using the existing verification environment and copied Excel fixtures.
Expected: all collected tests pass, with only the pre-existing integration skip.

- [ ] **Step 2: Run frontend full suite and build**

Run from `frontend`: `npm test -- --run` and `npm run build`.
Expected: all tests pass and Vite build succeeds.

- [ ] **Step 3: Run static checks**

Run: `git diff --check`; compile changed Python modules with `python -m py_compile`; verify no secrets or full contract/knowledge text are logged.

- [ ] **Step 4: Commit documentation or test-only corrections**

```bash
git add backend/README.md docs/superpowers/specs/2026-09-01-contract-ai-evidence-review-design.md
git commit -m "docs: document contract evidence review behavior"
```

- [ ] **Step 5: Report release handoff**

Provide the final commit SHA, test counts, endpoint compatibility, and explicit note that production deployment requires the clean worktree only.
