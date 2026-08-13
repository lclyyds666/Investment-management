# Unified Organization Production Release Design

## Goal

Publish the completed unified organization, position-permission, and position-aware workflow implementation to GitHub `main` and the production server without touching the user's dirty primary checkout or guessing designated people for legacy approvals.

## Release Boundary

- Integrate from `origin/main` in an isolated release worktree.
- Merge `feat/unified-organization-permissions` into the release branch.
- Update the root `README.md` so the documented organization model, positions, permission behavior, approval chains, migrations, and iteration log match the implementation.
- Push the tested release commit directly to GitHub `main`, as explicitly requested by the user.
- Deploy the exact GitHub `main` revision to `/opt/sd-scm` and record it in `/opt/sd-scm/REVISION` and `/opt/sd-scm/RELEASE`.

## Safety Constraints

- Do not stage, restore, overwrite, or delete files in the dirty primary checkout.
- Do not include ignored Excel fixtures, local deployment helpers, generated documents, secrets, `.env`, `.venv`, uploads, or database credentials in Git or release archives.
- Back up the production database and currently deployed application before migrations or file switching.
- Run organization-assignment and active-workflow migrations in preview mode before applying them.
- If any migration preview contains an unresolved row, `needs_designation`, or `invalid_state`, stop the release before switching production code and keep the existing production application active.
- Never choose a designated person automatically when the data has zero or multiple eligible candidates.
- Preserve production `.env`, `.venv`, uploads, and existing operational data.
- Any failed migration, import check, service start, health check, or acceptance check must stop the release and restore the previous application and database as applicable.

## Integration And Documentation

The release worktree starts at the current remote `main`. The completed feature branch is merged there so the release commit includes the full organization authorization foundation, system-management console, position-aware workflows, and final race-condition fixes. The root README is updated in the same release branch, including the three-company hierarchy, multi-position permission union, shared versus designated workflow nodes, superuser boundaries, new migrations, operational migration sequence, and a 2026-08-13 production iteration entry.

## Verification

Before pushing or deploying:

- Backend: all `unittest` tests pass with the two ignored Excel fixtures copied into the isolated release worktree for test use only.
- Frontend: all Vitest tests pass and the Vite production build succeeds.
- Git: `git diff --check` passes and only intended committed files differ from `origin/main`.

## Production Data Flow

1. Inspect production service, revision, database, and filesystem state without mutation.
2. Upload versioned release archives and migration helpers to `/tmp`.
3. Create a timestamped database dump and application rollback snapshot.
4. Extract the candidate release into a versioned staging directory and run a Python import check against production configuration.
5. Apply schema migrations in order: authorization audit context, unified organization permissions, then position workflow engine.
6. Run organization-assignment migration preview. Stop if unresolved rows exist; otherwise apply it and preserve both reports.
7. Run active-workflow preview. Stop if any pending row requires designation or is invalid; otherwise apply it and preserve both reports.
8. Switch backend application, scripts, migrations, requirements, deployment files, and frontend dist to the tested revision while preserving runtime secrets and uploads.
9. Restart the backend, reload Nginx, and run health, route, process, Redis, migration, and authenticated acceptance checks.
10. Write the exact GitHub `main` SHA to production revision markers only after all checks pass.

## Rollback

Application files are restored from the versioned rollback snapshot if switching or acceptance fails. Database rollback uses the pre-release SQL dump when a failure occurs after schema or data migration; this is deliberately slower but preserves the pre-release state. The release artifacts and reports remain on the server for audit until acceptance is complete.

## Success Criteria

- GitHub `main`, local release HEAD, `/opt/sd-scm/REVISION`, and `/opt/sd-scm/RELEASE` contain the same commit SHA.
- Backend and frontend production services are healthy.
- The unified system-management pages and permission snapshot APIs are reachable.
- Organization and workflow migration reports contain no unresolved rows.
- No user-owned local changes are staged or overwritten.
