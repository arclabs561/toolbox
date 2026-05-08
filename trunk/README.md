# trunk

Print the trunk branch of the current git repo.

Different repos call their default branch different things: `main`,
`develop`, `trunk`, `master`. Hardcoding `main` in scripts and CI checks
silently fails on the others. `trunk` derives the right answer.

## Usage

```sh
trunk            # main, develop, trunk, ...
trunk --remote   # origin/develop
trunk --refresh  # refresh origin/HEAD from the remote first
```

## Resolution order

1. `git symbolic-ref refs/remotes/origin/HEAD` (cached locally).
2. `git ls-remote --symref origin HEAD` (asks the remote, no write).
3. First match in `main`, `develop`, `trunk`, `master` among local branches.
4. Fallback: `main`.

## Why

Replaces patterns like:

```sh
gh run list --branch main --limit 1
```

with the trunk-aware form:

```sh
gh run list --branch "$(trunk)" --limit 1
```
