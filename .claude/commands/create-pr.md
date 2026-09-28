---
name: create-pr
description: Create a PR with changelog update, feature branch, commit, and push
---

# Create a Pull Request

Whenever the user asks to "create a PR" or "make a PR", follow **all** of these steps in order.

## Steps

### 1. Update `CHANGELOG.md`

Update `CHANGELOG.md` with the new changes:

- Under `## [Unreleased]`, add or update the version section `## [X.Y.Z] — YYYY-MM-DD`.
- Categorize changes into:
  - `### Added` — new features, services, endpoints
  - `### Changed` — modifications to existing behavior or configuration
  - `### Fixed` — bug fixes, timeout resolutions, connection pool fixes
- Each bullet should describe the change clearly with file paths in parentheses.
- Update comparison links at the bottom of `CHANGELOG.md`.

### 2. Create a feature branch

```bash
git checkout -b feat/<descriptive-name>
# or for bug fixes:
git checkout -b fix/<descriptive-name>
```

- If already on a feature branch (not `master`/`main`), skip this step and use the current branch.

### 3. Stage and commit

```bash
git add <changed-files>
git commit -m "<type>(<scope>): <summary>

<detailed description of changes>"
```

### 4. Push and provide PR link

```bash
git push -u origin <branch-name>
```

Output the PR creation URL:

```
https://github.com/thinhpm/tracking_meme/pull/new/<branch-name>
```
