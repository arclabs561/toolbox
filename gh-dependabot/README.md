# gh-dependabot

Inventory open Dependabot alerts across an owner's public, non-fork repositories.
Archived repositories are included.

The command is read-only. It uses the existing `gh` authentication and makes no
changes to repositories or alerts.

## Usage

```sh
gh-dependabot
gh-dependabot --owner arclabs561
gh-dependabot --json
```

Human output is tab-separated. JSON output includes normalized alert details and
per-repository API errors.

## Exit codes

- `0`: scan completed with no open alerts
- `1`: scan completed with one or more open alerts
- `2`: scan was incomplete because setup or an API request failed

An incomplete scan never reports success, even if the repositories that did
respond had no alerts.
