# commit-survey

Survey a git repo's commit, branch, and merge conventions.

Quick-orients an unfamiliar repo by measuring how the team writes
commits, names branches, and ships work. Replaces parametric-memory
guesswork with one read pass over local git state.

## Usage

```sh
commit-survey                 # current repo, last 500 commits
commit-survey -n 1000         # last 1000 commits
commit-survey --window '90 days ago'
commit-survey /path/to/repo
```

## Output

- Trunk branch (via `git symbolic-ref`)
- Merge strategy (merge commits vs squash/rebase, inferred from parent
  counts on merge commits)
- Scope-prefix histogram (`pkg:`, `path/to/pkg:`, ...)
- Ticket syntax (`W-XXXXX`, `JIRA-XXXX`, `LIN-XXXX`) — count, unique,
  and what fraction sit at the title start
- Trailers in bodies (`Fixes:`, `Closes:`, `Co-authored-by:`)
- Subject-casing convention after the scope or ticket prefix
- Branch-prefix families (`hw/`, `release/`, `magic/`, ...)
- Commit-body presence rate (% with prose beyond the subject)

## Why

Useful when:

- Onboarding to an unfamiliar repo and you want to match local style.
- Auditing your own repo's drift from documented conventions.
- Picking the right scope shape before drafting a commit.
