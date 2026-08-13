# Unified Organization Production Release Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Merge the completed unified organization and workflow branch, update project documentation, push the tested revision to GitHub `main`, and deploy that exact revision safely to production.

**Architecture:** Work only in an isolated release worktree based on `origin/main`, merge the completed feature branch, and package immutable release artifacts. Production deployment uses preview-first migrations, versioned backups, staged import checks, an atomic application switch, and explicit rollback paths.

**Tech Stack:** Git, PowerShell, Python 3.10+, FastAPI, SQLAlchemy 2.0, MySQL 8.0, Vue 3, Vite, Vitest, SSH/SCP, systemd, Nginx.

## Global Constraints

- Do not stage, restore, overwrite, or delete files in the dirty primary checkout.
- Push only the fully tested release HEAD to GitHub `main`.
- Preserve production `.env`, `.venv`, uploads, MySQL credentials, and secrets.
- Back up the production database and deployed application before any migration or file switch.
- Stop the release and keep the existing production application active if an organization or workflow preview contains unresolved rows, `needs_designation`, or `invalid_state`.
- Never guess a designated person when zero or multiple candidates are eligible.
- Copy ignored Excel fixtures only for local tests; never stage or archive them.
- Record production revision markers only after all production acceptance checks pass.

---

### Task 1: Integrate Feature And Documentation

**Files:**
- Modify: `README.md`
- Create: `docs/superpowers/specs/2026-08-13-unified-organization-production-release-design.md`
- Create: `docs/superpowers/plans/2026-08-13-unified-organization-production-release.md`

**Interfaces:**
- Consumes: branch `feat/unified-organization-permissions` at `dba76fc` and `origin/main`.
- Produces: one release branch containing the full feature and current operational documentation.

- [ ] **Step 1: Merge the completed feature branch**

Run:

```powershell
git merge --no-ff feat/unified-organization-permissions -m "merge: unified organization permissions"
```

Expected: a merge commit with no unresolved conflicts.

- [ ] **Step 2: Update README operational truth**

Replace the legacy eight-role description and static role-based approval chains with:

- investment company hierarchy and positions;
- supply company and foundation company positions;
- permission union across effective assignments;
- shared-position versus designated-person workflow nodes;
- superuser approval restrictions and reassignment authority;
- the three new migration files and preview/apply commands;
- a `2026-08-13` iteration entry marked pending until production acceptance.

- [ ] **Step 3: Check and commit documentation**

Run:

```powershell
git diff --check
git add -- README.md docs/superpowers/specs/2026-08-13-unified-organization-production-release-design.md docs/superpowers/plans/2026-08-13-unified-organization-production-release.md
git commit -m "docs: document unified organization release"
```

Expected: only intended release documentation is committed.

### Task 2: Run Release Verification

**Files:**
- Test: `backend/tests`
- Test: `frontend/src/**/*.test.js`
- Build: `frontend/dist`

**Interfaces:**
- Consumes: integrated release HEAD.
- Produces: green backend, frontend, and production-build gates.

- [ ] **Step 1: Supply ignored test fixtures**

Copy these files from the primary checkout to the identical relative paths in the release worktree and verify SHA-256 equality:

```text
泉州酒店/2026.1.1-1.25明细.xlsx
台账/对账明细-2026.04.29-2026.05.19.xlsx
```

- [ ] **Step 2: Run backend tests**

Run from `backend`:

```powershell
& 'D:\Investment-management\backend\.venv\Scripts\python.exe' -m unittest discover -s tests -v
```

Expected: all 343 tests pass.

- [ ] **Step 3: Run frontend tests and build**

Run from `frontend`:

```powershell
npm test
npm run build
```

Expected: all Vitest tests pass and Vite builds successfully.

- [ ] **Step 4: Verify release tree**

Run:

```powershell
git diff --check
git status --short --untracked-files=all
git log -5 --oneline
```

Expected: no tracked modifications; ignored Excel fixtures do not appear.

### Task 3: Push Exact Release To GitHub Main

**Files:**
- Remote branch: `origin/main`

**Interfaces:**
- Consumes: tested release HEAD.
- Produces: GitHub `main` pointing at the exact release SHA.

- [ ] **Step 1: Confirm remote main has not moved**

Run:

```powershell
git ls-remote origin refs/heads/main
git rev-parse origin/main
```

Expected: both identify the integration base `21bca0b9968e997438f7b0fb883d219c38ad5d1f`. If remote `main` moved, stop and re-integrate instead of force-pushing.

- [ ] **Step 2: Push release HEAD**

Run:

```powershell
git push origin HEAD:main
git ls-remote origin refs/heads/main
git rev-parse HEAD
```

Expected: GitHub `main` and local HEAD have the same full SHA.

### Task 4: Stage Production Release And Preflight

**Files:**
- Deploy: `backend/app`, `backend/scripts`, `backend/migrations`, `backend/requirements.txt`, `deploy`, `frontend/dist`, `README.md`
- Preserve: `/opt/sd-scm/backend/.env`, `/opt/sd-scm/backend/.venv`, `/opt/sd-scm/backend/uploads`

**Interfaces:**
- Consumes: exact GitHub `main` revision.
- Produces: versioned candidate release and verified rollback backups.

- [ ] **Step 1: Inspect production state read-only**

Check the current revision markers, service status, MySQL connectivity, disk space, `/opt/sd-scm` ownership, Python version, and pending legacy workflow counts. Do not mutate production.

- [ ] **Step 2: Build versioned archives**

Create archives from the release worktree only:

```powershell
tar -czf release-app.tgz -C backend app scripts migrations requirements.txt README.md
tar -czf release-dist.tgz -C frontend/dist .
tar -czf release-ops.tgz deploy README.md
```

Upload them to `/tmp/sd-scm-<revision>-*.tgz`.

- [ ] **Step 3: Create production backups**

Create:

- `/opt/sd-scm/backups/pre-unified-org-<revision>.sql` using `mysqldump --single-transaction`;
- `/opt/sd-scm/releases/<revision>/rollback` containing current backend app/scripts/migrations/requirements, frontend dist, deploy files, README, and current revision markers.

Verify that the SQL dump is non-empty and the rollback directories exist before continuing.

- [ ] **Step 4: Stage and import-check candidate**

Extract candidate files into `/opt/sd-scm/releases/<revision>/candidate`, install requirements into the existing virtual environment, and run:

```bash
cd /opt/sd-scm/backend
PYTHONPATH=/opt/sd-scm/releases/<revision>/candidate/backend .venv/bin/python -c 'import app.main'
```

Expected: import succeeds without replacing the active application.

### Task 5: Preview And Apply Production Migrations

**Files:**
- Apply: `backend/migrations/20260813_authorization_audit_context.sql`
- Apply: `backend/migrations/20260813_unified_organization_permissions.sql`
- Apply: `backend/migrations/20260814_position_workflow_engine.sql`
- Run: `backend/scripts/migrate_company_roles_to_assignments.py`
- Run: `backend/scripts/migrate_active_workflows.py`

**Interfaces:**
- Consumes: production database and staged candidate scripts.
- Produces: migrated organization assignments and safely materialized active workflows, or a stopped release with current production still active.

- [ ] **Step 1: Pause business submissions**

Enable a temporary Nginx maintenance rule for contract and approval submission POST routes while leaving health and read-only traffic available. Validate Nginx configuration before reload.

- [ ] **Step 2: Apply schema migrations**

Run the three SQL migrations in timestamp order using credentials read inside the production environment without printing them.

- [ ] **Step 3: Preview organization assignment migration**

Run from the staged backend with production environment:

```bash
python scripts/migrate_company_roles_to_assignments.py --report /opt/sd-scm/releases/<revision>/organization-preview.json
```

Expected: exit code `0` and no unresolved rows. Exit code `2` or unresolved rows stops the release and triggers database rollback before the maintenance rule is removed.

- [ ] **Step 4: Apply organization assignment migration**

Run `--apply` to `organization-applied.json`, then confirm it reports no unresolved rows.

- [ ] **Step 5: Preview active workflow migration**

Run:

```bash
python -m scripts.migrate_active_workflows --report /opt/sd-scm/releases/<revision>/workflow-preview.json
```

Expected: no `needs_designation` or `invalid_state` pending rows. Any such row stops the release and restores the database backup; no designated person is guessed.

- [ ] **Step 6: Apply active workflow migration**

Run `--apply` to `workflow-applied.json`, then verify no pending contract or approval form lacks `workflow_instance_id`.

### Task 6: Switch And Accept Production

**Files:**
- Switch: candidate release files into `/opt/sd-scm`
- Write: `/opt/sd-scm/REVISION`, `/opt/sd-scm/RELEASE`

**Interfaces:**
- Consumes: successful migration reports and candidate release.
- Produces: healthy production serving the exact GitHub `main` revision.

- [ ] **Step 1: Switch application files**

Stop `sd-scm-backend`, replace only versioned application/deployment files from candidate, preserve `.env`, `.venv`, uploads and data directories, normalize ownership to `www-data`, then start the service.

- [ ] **Step 2: Reload frontend and Nginx**

Replace `frontend/dist`, validate `nginx -t`, remove the temporary submission maintenance rule, and reload Nginx.

- [ ] **Step 3: Run acceptance checks**

Require:

- `sd-scm-backend.service` active with two Uvicorn workers;
- Redis `PONG`;
- `/api/v1/health` HTTP 200 and shared AI store ready;
- `/`, `/supplymanagement`, `/investment`, `/fundmanagement`, and unified system-management routes HTTP 200;
- organization permission snapshot, position directory, workflow candidate/task endpoints respond correctly under authenticated smoke identities;
- organization and workflow applied reports contain no unresolved records;
- recent backend journal contains no startup exceptions or migration tracebacks.

- [ ] **Step 4: Publish revision markers**

Write the exact release SHA to `/opt/sd-scm/REVISION` and `/opt/sd-scm/RELEASE`, then verify both equal GitHub `main` and local release HEAD.

- [ ] **Step 5: Mark README iteration deployed**

If the pre-push README entry was marked pending, change it to `生产 ✅`, commit, push the documentation-only follow-up to `main`, and update production README plus revision markers to the follow-up SHA without changing application artifacts.

- [ ] **Step 6: Preserve audit artifacts**

Keep the database dump, rollback application snapshot, migration preview/apply reports, and release manifest under `/opt/sd-scm/releases/<revision>`; delete only version-matched `/tmp` upload archives after acceptance.
