# Unified Organization MySQL Collation Fix Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the unified organization schema migration compatible with the production MySQL 8 collation and safely resume the gated production release.

**Architecture:** Keep the fix at the schema boundary by declaring `utf8mb4_unicode_ci` on every new unified-organization table. Protect the invariant with a static migration test, then rebuild immutable artifacts from the new commit and rerun all migration previews against an isolated production database copy before any production switch.

**Tech Stack:** MySQL 8.0.46 SQL migrations, Python 3.13, pytest 8.3.5, Vue 3, Vitest 3.2.7, Vite, Git, SSH.

## Global Constraints

- Do not modify the dirty primary checkout at `D:\Investment-management`.
- Do not change any role, permission, workflow, assignment, or external-counsel business rule.
- Do not change production database or server default collations.
- Never guess an external legal counsel effective end date or a designated workflow user.
- Stop before applying production changes if any preview reports `unresolved`, `needs_designation`, `invalid_state`, or an SQL error.
- Preserve production `.env`, `.venv`, uploads, data, current application files, and active services until every preview gate passes.
- Push without force and deploy only the exact GitHub `main` commit that passed verification.

---

### Task 1: Lock The Schema Collation Invariant

**Files:**
- Modify: `backend/tests/test_workflow_models.py`
- Modify: `backend/migrations/20260813_unified_organization_permissions.sql`

**Interfaces:**
- Consumes: `migrations/20260813_unified_organization_permissions.sql` as UTF-8 text.
- Produces: seven unified-organization `CREATE TABLE` statements whose table options include `DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci`.

- [ ] **Step 1: Write the failing static migration test**

Add this method to `WorkflowModelTest` in `backend/tests/test_workflow_models.py`:

```python
def test_unified_organization_tables_use_production_collation(self):
    source = Path(
        "migrations/20260813_unified_organization_permissions.sql"
    ).read_text(encoding="utf-8")
    table_options = [
        line.strip()
        for line in source.splitlines()
        if line.strip().startswith(") ENGINE=InnoDB DEFAULT CHARSET=utf8mb4")
    ]
    self.assertEqual(len(table_options), 7)
    for table_option in table_options:
        self.assertIn("COLLATE=utf8mb4_unicode_ci", table_option)
```

- [ ] **Step 2: Run the focused test and verify it fails**

Run from `backend`:

```powershell
& 'D:\Investment-management\.release-artifacts\43f417bcd9076abc8e3637d974e9549c477fd3bf\verify-venv\Scripts\python.exe' -m pytest tests/test_workflow_models.py::WorkflowModelTest::test_unified_organization_tables_use_production_collation -q
```

Expected: one failure because the seven table options omit `COLLATE=utf8mb4_unicode_ci`.

- [ ] **Step 3: Apply the minimal SQL fix**

Replace every occurrence in `backend/migrations/20260813_unified_organization_permissions.sql`:

```sql
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT=
```

with:

```sql
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT=
```

Do this for exactly the seven new organization-domain tables:
`sys_organization`, `sys_position`, `sys_permission`, `sys_user_assignment`,
`sys_position_permission`, `sys_governance_scope`, and `sys_external_assignment`.

- [ ] **Step 4: Run focused migration tests**

Run from `backend`:

```powershell
& 'D:\Investment-management\.release-artifacts\43f417bcd9076abc8e3637d974e9549c477fd3bf\verify-venv\Scripts\python.exe' -m pytest tests/test_workflow_models.py -q
```

Expected: all tests in `test_workflow_models.py` pass.

- [ ] **Step 5: Run all local release verification**

Run backend tests from `backend`:

```powershell
& 'D:\Investment-management\.release-artifacts\43f417bcd9076abc8e3637d974e9549c477fd3bf\verify-venv\Scripts\python.exe' -m pytest -q
```

Run frontend tests and build from `frontend`:

```powershell
npm test -- --run
npm run build
```

Expected: backend has 344 passing tests, frontend has 203 passing tests, and Vite build exits zero.

- [ ] **Step 6: Commit the tested fix**

```powershell
git add -- backend/tests/test_workflow_models.py backend/migrations/20260813_unified_organization_permissions.sql
git commit -m "fix: align unified organization table collations"
```

---

### Task 2: Publish And Rebuild The Exact Release

**Files:**
- Push: current release branch HEAD to `origin/main`
- Create: `D:\Investment-management\.release-artifacts\<revision>\sd-scm-<revision>-app.tgz`
- Create: `D:\Investment-management\.release-artifacts\<revision>\sd-scm-<revision>-dist.tgz`
- Create: `D:\Investment-management\.release-artifacts\<revision>\sd-scm-<revision>-ops.tgz`

**Interfaces:**
- Consumes: the tested commit from Task 1 and the committed release documentation.
- Produces: GitHub `main` and three SHA-256-verified release artifacts containing that exact commit.

- [ ] **Step 1: Verify worktree cleanliness and push without force**

```powershell
git status --short
git push origin HEAD:main
git ls-remote origin refs/heads/main
```

Expected: the worktree is clean and remote `main` equals local `git rev-parse HEAD`.

- [ ] **Step 2: Rebuild production frontend**

```powershell
Set-Location frontend
npm run build
Set-Location ..
```

Expected: `frontend/dist/index.html` and hashed assets are rebuilt successfully.

- [ ] **Step 3: Create versioned archives**

Set `$revision` to `git rev-parse HEAD`, create
`D:\Investment-management\.release-artifacts\$revision`, and run:

```powershell
tar -czf "$artifactRoot\sd-scm-$revision-app.tgz" -C backend app scripts migrations requirements.txt README.md
tar -czf "$artifactRoot\sd-scm-$revision-dist.tgz" -C frontend\dist .
tar -czf "$artifactRoot\sd-scm-$revision-ops.tgz" deploy README.md
Get-FileHash -Algorithm SHA256 "$artifactRoot\sd-scm-$revision-*.tgz"
```

Expected: three non-empty archives and three recorded SHA-256 hashes.

- [ ] **Step 4: Upload and verify artifacts**

Upload the archives to `/tmp/` with `scp`, then run server-side `sha256sum`.

Expected: every server hash matches its local hash.

---

### Task 3: Rerun The Isolated Production Preview

**Files:**
- Create: `/opt/sd-scm/backups/pre-unified-org-<revision>.sql`
- Create: `/opt/sd-scm/releases/<revision>/candidate`
- Create: `/opt/sd-scm/releases/<revision>/rollback`
- Create: `/opt/sd-scm/releases/<revision>/organization-preview.json`

**Interfaces:**
- Consumes: current production database, current production files, and Task 2 artifacts.
- Produces: an isolated organization migration report and either a clean gate or a precise blocking record.

- [ ] **Step 1: Revalidate production baseline**

Verify the active revision is still
`63b2db4e7f3a2179bdf67bd5284b88da88d7d83a`, all four services are active,
the health endpoint is healthy, and the new release/backup paths do not exist.

- [ ] **Step 2: Create versioned rollback assets**

Use `mysqldump --single-transaction --routines --triggers --events --no-tablespaces`
for the production database. Copy only current versioned application files into
`/opt/sd-scm/releases/<revision>/rollback`; do not copy `.env`, `.venv`, uploads,
or data directories.

Expected: the SQL dump is non-empty and rollback directories exist.

- [ ] **Step 3: Restore an isolated database with production collation**

Create a uniquely named temporary database using
`CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci`, grant the existing application
database account access only to that database, restore the versioned dump, and
install an exit trap that revokes the temporary grant and drops the temporary database.

- [ ] **Step 4: Apply all candidate schema migrations to the temporary database**

Run these in order:

```text
20260813_authorization_audit_context.sql
20260813_unified_organization_permissions.sql
20260814_position_workflow_engine.sql
```

For the isolated copy only, remove the fixed `USE sd_publish_scm` statement from
the input stream so it cannot select the production schema. Do not edit the archived SQL.

Expected: all three migrations exit zero and the candidate backend imports successfully.

- [ ] **Step 5: Seed and preview legacy assignments**

Run `seed_authorization_catalog`, commit it only in the temporary database, then run:

```bash
python -m scripts.migrate_company_roles_to_assignments --report <release-root>/organization-preview.json
```

Expected release gate: exit zero and no unresolved rows. Expected current production-data outcome: exit two for user `legal` because the external legal counsel effective end date requires administrator confirmation.

- [ ] **Step 6: Enforce the stop gate**

If the preview exits two or contains any unresolved row:

1. Do not apply migrations to the production database.
2. Do not stop or restart services.
3. Do not switch candidate files.
4. Confirm the temporary database and grant were removed.
5. Confirm the production revision, health, and service states remain unchanged.
6. Report the exact username, legacy role, and reason to the user for a business decision.

Only if the organization preview is clean may the release continue to workflow publication, active workflow preview/apply, maintenance mode, production schema application, application switch, acceptance checks, README deployment status update, and final GitHub `main` documentation commit under the existing release plan.

