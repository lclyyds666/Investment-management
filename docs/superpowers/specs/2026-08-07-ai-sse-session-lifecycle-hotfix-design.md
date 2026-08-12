# AI SSE Session Lifecycle Hotfix Design

## Incident

The production smoke test returned HTTP 200 for the AI message stream but emitted no SSE events. The backend logged `DetachedInstanceError` before `message.created` because FastAPI closed the request-scoped database dependency before consuming the `StreamingResponse` body iterator. The iterator still held the closed request `Session` and expired ORM instances created before the response was returned.

The database migrations, Redis coordination, portal permissions, and non-streaming APIs are healthy. This hotfix is limited to the database-session boundary of AI message streaming.

## Selected Approach

The message endpoint will capture the request session's SQLAlchemy bind and the scalar identifiers needed by the stream. It will return a wrapper iterator that creates a new SQLAlchemy session when streaming actually begins, reloads the conversation and message rows by ID, constructs the existing permission-aware user context from captured scalar identity fields, and delegates to the existing generation iterator. The stream-owned session remains open until the delegated iterator completes or is cancelled, then closes normally.

This preserves the existing SSE protocol, provider-output validation, Redis leases, stop behavior, persistence, and permission queries. It also works with the current SQLite test engine because the stream session is created from the request session's bind rather than a hard-coded global engine.

## Alternatives Considered

Changing `get_db` to delay dependency cleanup was rejected because modern FastAPI intentionally closes yielded dependencies before response streaming. Overriding that lifecycle would be framework-sensitive and could leak pooled connections for unrelated endpoints.

Buffering the complete AI answer before returning was rejected because it would remove incremental SSE behavior and make active generation stop requests ineffective.

Keeping detached ORM instances and reopening the closed request session was rejected because detached changes are not guaranteed to be tracked or committed, and it would continue to rely on undocumented session reuse behavior.

## Data Flow

1. The authenticated endpoint validates conversation ownership and calls `begin_generation` in the request session.
2. `begin_generation` persists the user and assistant message rows and acquires the existing Redis generation lease.
3. Before returning the response, the endpoint captures the engine bind, conversation ID, both message IDs, user ID, superuser flag, lease, and request ID.
4. When Uvicorn consumes the response iterator, the wrapper opens a fresh session from that bind and reloads the three persisted rows.
5. The wrapper delegates to `stream_generation`, which emits the unchanged SSE events and performs the unchanged tool, stop, heartbeat, validation, and settlement logic.
6. The wrapper closes its session after the stream finishes. The core iterator remains responsible for clearing the stop flag and releasing the generation lease.

## Error Handling

The wrapper validates that all persisted rows still exist and belong to the captured conversation before delegation. If initialization fails, it emits one sanitized SSE error, clears the stop flag, and releases the lease exactly once so a conversation cannot remain busy. After delegation begins, the existing core iterator remains the sole owner of terminal SSE events and coordination cleanup. Exceptions raised after delegation, including Redis or session cleanup failures after a terminal event, propagate to the server layer without the wrapper appending a second terminal event.

Cancellation propagates through the existing core iterator after it settles the message as stopped and releases coordination state. The wrapper closes the stream-owned session in every exit path.

## Verification

A regression test will create a response, close the request session before consuming `body_iterator`, then assert that `message.created`, validated content, and a terminal event are emitted and persisted. Initialization-failure coverage will require one sanitized terminal error and one lease release. Delegated-cleanup failure coverage will require that a previously emitted terminal event is not followed by another SSE error. Existing streaming tests continue to exercise completion, stop, disconnect, cancellation, lease renewal, provider validation, and settlement behavior.

Before redeployment, run all 149+ backend tests, all 113 frontend tests, the production frontend build, both Playwright portal tests, and `git diff --check`. Production verification repeats the authenticated portal and AI smoke test, checks two Uvicorn workers, Redis readiness, the cleanup timer, all four portal routes, sanitized logs, and matching GitHub/production revision markers.

## Deployment And Rollback

The hotfix is committed and pushed as a new revision. Production receives a new staged release containing the updated backend `app`; the current deployed app remains in the existing release rollback area until the new SSE smoke test passes. No additional schema change is required. If health or streaming verification fails, restore the prior app directory and restart the already installed service definition.
