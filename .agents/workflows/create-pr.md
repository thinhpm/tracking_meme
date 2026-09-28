---
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
- Each bullet should describe the change clearly with file paths in parentheses (e.g. `api/app/services/...`).
- Update comparison links at the bottom of `CHANGELOG.md` for semantic versioning.

### 2. Create a feature branch

```bash
git checkout -b feat/<descriptive-name>
# or for bug fixes:
git checkout -b fix/<descriptive-name>
```

- Use a short, descriptive branch name based on the feature/fix.
- If already on a feature branch (not `master`/`main`), skip this step and use the current branch.

### 3. Stage and commit

```bash
git add <changed-files>
git commit -m "<type>(<scope>): <summary>

<detailed description of changes>"
```

- **Type**: `feat`, `fix`, `docs`, `refactor`, `chore`
- **Scope**: the module or area (e.g., `llm`, `bot`, `api`, `docker`)
- Commit message body should list all changed files and what they do.

### 4. Push and provide PR link

```bash
git push -u origin <branch-name>
```

Output the PR creation URL for the user:

```
https://github.com/thinhpm/tracking_meme/pull/new/<branch-name>
```

## Template: Commit Message

```
<type>(<scope>): <one-line summary>

Changes:
- file1.py: description
- file2.py: description
```

## Template: Changelog Entry

```markdown
## [X.Y.Z] — YYYY-MM-DD

### Added
- **Feature Name** (`path/to/file.py`):
  - Detail about what changed.
  - Another detail.

### Fixed
- **Bug Fix Name** (`path/to/file.py`): Description.
```

## Important Notes

- Always check `git branch` first — if already on a feature branch, don't create a new one.
- Always check `git status` to know which files are modified/untracked.
- Only stage files relevant to the current feature — don't include secrets, `.env`, or temporary files.
- Ensure all tests pass (`pytest`) before committing.
