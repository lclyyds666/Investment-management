# AI SSE Session Lifecycle Hotfix Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Keep a valid SQLAlchemy session open for the complete AI SSE response lifecycle so production streams emit and persist their events after FastAPI closes request dependencies.

**Architecture:** The request endpoint persists the generation records as it does today, captures scalar IDs and its engine bind, and returns a wrapper iterator. The wrapper opens a new session when the response body is consumed, reloads the persisted records, delegates to the existing generation iterator, and closes the session after completion or cancellation.

**Tech Stack:** Python 3.10+, FastAPI 0.115.6, SQLAlchemy 2.0.36, Uvicorn workers, Redis coordination, `unittest`.

## Global Constraints

- Do not change the SSE event names or JSON payload contract.
- Do not log prompt text, answer text, credentials, tokens, SQL, or raw business rows.
- Keep Redis lease, heartbeat, stop, provider-output validation, and settlement behavior unchanged.
- Emit exactly one terminal SSE event per stream; the wrapper may emit an error only before delegation starts.
- Release each generation lease from exactly one owner: the wrapper before delegation or the core iterator after delegation.
- Do not add dependencies or database migrations.
- Preserve `/opt/sd-scm/backend/.env`, `.venv`, and `uploads` during deployment.

---

### Task 1: Reproduce Request-Session Cleanup

**Files:**
- Modify: `backend/tests/test_ai_streaming.py`
- Test: `backend/tests/test_ai_streaming.py`

**Interfaces:**
- Consumes: `stream_message(...) -> StreamingResponse` and its asynchronous `body_iterator`.
- Produces: `AiStreamingEndpointTest.test_stream_uses_a_fresh_session_after_request_cleanup`.

- [ ] **Step 1: Write the failing regression test**

Add this method to `AiStreamingEndpointTest`:

```python
async def test_stream_uses_a_fresh_session_after_request_cleanup(self):
    payload = AiMessageCreate(content="session lifecycle", client_message_id=uuid4())
    with patch(
        "app.services.ai_conversations.AiOrchestrator",
        return_value=_OneDeltaOrchestrator(),
    ):
        response = await stream_message(
            conversation_id=self.conversation.id,
            payload=payload,
            request=_ConnectedRequest(),
            db=self.db,
            current_user=self.user,
        )
        self.db.close()
        frames = [frame async for frame in response.body_iterator]

    events = [_event(frame) for frame in frames]
    self.assertEqual(
        [name for name, _ in events],
        ["message.created", "text.delta", "message.completed"],
    )
    with Session(self.engine) as verification_db:
        assistant = verification_db.scalar(
            select(AiMessage).where(AiMessage.role == "assistant")
        )
        self.assertEqual(assistant.status, "completed")
        self.assertTrue(assistant.content)
```

- [ ] **Step 2: Run the focused test and confirm the production failure**

Run from `backend`:

```powershell
& 'D:\Investment-management\backend\.venv\Scripts\python.exe' -m unittest tests.test_ai_streaming.AiStreamingEndpointTest.test_stream_uses_a_fresh_session_after_request_cleanup -v
```

Expected: FAIL because the existing body iterator accesses detached `AiConversation` or `AiMessage` instances after `self.db.close()`.

### Task 2: Add A Stream-Owned Session Boundary

**Files:**
- Modify: `backend/app/services/ai_conversations.py`
- Modify: `backend/app/api/v1/endpoints/ai_assistant.py`
- Modify: `backend/tests/test_ai_streaming.py`
- Test: `backend/tests/test_ai_streaming.py`

**Interfaces:**
- Consumes: a `Callable[[], Session]`, persisted IDs, `GenerationLease`, request ID, request object, user ID, and superuser flag.
- Produces: `stream_generation_in_session(...) -> AsyncIterator[str]`.

- [ ] **Step 1: Add the stream-owned session wrapper**

In `backend/app/services/ai_conversations.py`, extend the typing import with `Callable`, import `SimpleNamespace`, and add this wrapper immediately before `stream_generation`:

```python
async def stream_generation_in_session(
    *,
    session_factory: Callable[[], Session],
    conversation_id: int,
    user_message_id: int,
    assistant_message_id: int,
    lease: ai_runtime.GenerationLease,
    request_id: str,
    request,
    user_id: int,
    is_superuser: bool,
) -> AsyncIterator[str]:
    delegated = False
    try:
        with session_factory() as db:
            conversation = db.get(AiConversation, conversation_id)
            user_message = db.get(AiMessage, user_message_id)
            assistant_message = db.get(AiMessage, assistant_message_id)
            if (
                conversation is None
                or conversation.owner_id != user_id
                or user_message is None
                or user_message.conversation_id != conversation_id
                or user_message.role != "user"
                or assistant_message is None
                or assistant_message.conversation_id != conversation_id
                or assistant_message.role != "assistant"
            ):
                raise RuntimeError("AI generation records could not be reloaded")
            delegated = True
            stream_user = SimpleNamespace(id=user_id, is_superuser=is_superuser)
            async for frame in stream_generation(
                db=db,
                conversation=conversation,
                user_message=user_message,
                assistant_message=assistant_message,
                lease=lease,
                request_id=request_id,
                request=request,
                user=stream_user,
            ):
                yield frame
    except (asyncio.CancelledError, GeneratorExit):
        raise
    except Exception:
        logger.exception(
            "ai_generation_session_failed",
            extra={
                "request_id": request_id,
                "message_id": assistant_message_id,
                "conversation_id": conversation_id,
            },
        )
        if delegated:
            raise
        yield encode_sse(
            "error",
            _event_payload(
                request_id,
                assistant_message_id,
                {
                    "status": "failed",
                    "code": "persistence_failed",
                    "message": "AI 服务暂时不可用，请稍后重试。",
                },
            ),
        )
    finally:
        if not delegated:
            ai_runtime.clear_stop_request(assistant_message_id)
            ai_runtime.release_generation(lease)
```

- [ ] **Step 2: Make the endpoint pass only stable stream inputs**

In `backend/app/api/v1/endpoints/ai_assistant.py`, import `sessionmaker`, replace the `stream_generation` import with `stream_generation_in_session`, and construct the iterator after `begin_generation`:

```python
    stream_session_factory = sessionmaker(bind=db.get_bind())
    iterator = stream_generation_in_session(
        session_factory=stream_session_factory,
        conversation_id=conversation.id,
        user_message_id=user_message.id,
        assistant_message_id=assistant_message.id,
        lease=lease,
        request_id=request_id,
        request=request,
        user_id=current_user.id,
        is_superuser=current_user.is_superuser,
    )
```

- [ ] **Step 3: Update the expired-lease assertion for the separate session**

Remove the `patch.object(self.db, "commit", ...)` wrapper and its `commit.call_count` assertion from `test_expired_generation_cannot_settle_over_successor`. Keep the existing assertions that the assistant row remains `generating`, its content remains empty, and the successor Redis lease remains owned; those assertions directly verify that settlement was rejected.

- [ ] **Step 4: Add wrapper ownership and terminal-cardinality regressions**

Add direct coverage that a session-factory initialization error emits one safe `error` and invokes `release_generation` once. Add delegated cleanup coverage that makes `release_generation` release successfully and then raise after `message.completed`; assert that consuming the next frame raises and that the three already emitted events contain exactly one terminal event. This proves the wrapper never appends a second `error` after delegation.

- [ ] **Step 5: Run the focused streaming module**

Run from `backend`:

```powershell
& 'D:\Investment-management\backend\.venv\Scripts\python.exe' -m unittest tests.test_ai_streaming -v
```

Expected: all streaming tests PASS, including the new request-cleanup regression.

- [ ] **Step 6: Run the complete backend suite**

Run from `backend`:

```powershell
& 'D:\Investment-management\backend\.venv\Scripts\python.exe' -m unittest discover -s tests -p 'test*.py' -v
```

Expected: all 152 backend tests PASS.

- [ ] **Step 7: Commit the implementation**

```powershell
git add -- backend/app/services/ai_conversations.py backend/app/api/v1/endpoints/ai_assistant.py backend/tests/test_ai_streaming.py docs/superpowers/plans/2026-08-07-ai-sse-session-lifecycle-hotfix.md
git commit -m "fix: keep AI stream database session alive"
```

### Task 3: Verify, Push, And Hot-Deploy

**Files:**
- Deploy: `backend/app`
- Preserve: `/opt/sd-scm/backend/.env`
- Preserve: `/opt/sd-scm/backend/.venv`
- Preserve: `/opt/sd-scm/backend/uploads`

**Interfaces:**
- Consumes: the committed backend `app` tree and the existing production service definitions.
- Produces: healthy production SSE, matching GitHub and production revision markers.

- [ ] **Step 1: Run unaffected frontend and repository gates**

```powershell
Set-Location frontend
npm test
npm run build
npm run test:e2e
Set-Location ..
git diff --check
git status --short
```

Expected: 113 frontend tests PASS, 2 Playwright tests PASS, the build succeeds, `git diff --check` is empty, and the worktree is clean.

- [ ] **Step 2: Push the exact hotfix commit to GitHub main**

```powershell
git push origin HEAD:main
git fetch origin
git rev-parse HEAD
git rev-parse origin/main
```

Expected: both revisions are identical.

- [ ] **Step 3: Stage and switch only the production backend app**

Create and upload the app-only archive:

```powershell
$revision = (git rev-parse HEAD).Trim()
$archive = "D:\Investment-management\.tmp-deploy-$revision-app.tgz"
tar -czf $archive -C backend app
scp $archive "root@39.107.52.146:/tmp/sd-scm-$revision-app.tgz"
```

On production, create `/opt/sd-scm/releases/$revision/backend`, extract the archive there, normalize directories to `0755` and files to `0644`, and import `app.main` with `/opt/sd-scm/backend/.venv/bin/python` while the production backend directory remains the working directory so `.env` is loaded. Copy the extracted app to `/opt/sd-scm/backend/app.next.$revision`. Stop `sd-scm-backend.service`, move `/opt/sd-scm/backend/app` to `/opt/sd-scm/releases/$revision/rollback/backend-app`, move the prepared directory to `/opt/sd-scm/backend/app`, and start the service. If health does not report `ai_shared_store=ready` within 30 seconds, move the failed app into the release rollback directory, restore `backend-app`, and restart the service. Do not replace `.env`, `.venv`, `uploads`, or `frontend/dist`.

- [ ] **Step 4: Repeat production acceptance**

Verify two Uvicorn workers, Redis `PONG`, `/api/v1/health` with `ai_shared_store=ready`, active/enabled cleanup timer, and HTTP 200 for `/`, `/supplymanagement`, `/investment`, and `/fundmanagement`. Run the authenticated smoke helper and require `auth_identity=ok`, `portal_applications=ok`, `portal_permissions=ok`, `conversation_create=ok`, `sse_stream=ok`, `message_stop=ok`, `conversation_cleanup=ok`, and `authenticated_smoke=ok`.

```powershell
ssh root@39.107.52.146 systemctl is-active sd-scm-backend.service
ssh root@39.107.52.146 redis-cli ping
ssh root@39.107.52.146 curl -fsS http://127.0.0.1:8000/api/v1/health
ssh root@39.107.52.146 systemctl is-active sd-scm-ai-cleanup.timer
ssh root@39.107.52.146 systemctl is-enabled sd-scm-ai-cleanup.timer
ssh root@39.107.52.146 'cd /opt/sd-scm/backend && PYTHONPATH=/opt/sd-scm/backend .venv/bin/python /tmp/sd-scm-d9860ff-smoke.py'
```

- [ ] **Step 5: Verify sanitized logs and publish revision markers**

Count, without printing matching lines, occurrences of the unique smoke prompt marker and sensitive-key patterns in the backend journal since the hotfix restart; require zero. Write the full hotfix SHA to `/opt/sd-scm/REVISION` and `/opt/sd-scm/RELEASE`, then confirm both markers, local HEAD, and GitHub `main` are identical.

```powershell
$revision = (git rev-parse HEAD).Trim()
ssh root@39.107.52.146 "printf '%s\n' '$revision' > /opt/sd-scm/REVISION; printf '%s\n' '$revision' > /opt/sd-scm/RELEASE"
git rev-parse HEAD
git rev-parse origin/main
ssh root@39.107.52.146 cat /opt/sd-scm/REVISION
ssh root@39.107.52.146 cat /opt/sd-scm/RELEASE
```

- [ ] **Step 6: Remove generated deployment helpers**

Delete only the known local `.tmp-deploy-d9860ff-*` files and their matching `/tmp/sd-scm-d9860ff-*` remote helpers after production verification. Identify the SSH process listening on local port `1081` and stop only that SOCKS tunnel; do not terminate PID `29992` or unrelated SSH sessions.

```powershell
Get-NetTCPConnection -LocalAddress 127.0.0.1 -LocalPort 1081 -State Listen | Select-Object -ExpandProperty OwningProcess
ssh root@39.107.52.146 'rm -f /tmp/sd-scm-d9860ff-db.py /tmp/sd-scm-d9860ff-switch.sh /tmp/sd-scm-d9860ff-smoke.py'
```
