# toolbox

Simple CLI tools. Each lives in its own directory; `bin/` has symlinks for PATH.

## Setup

```sh
# add to your shell profile
export PATH="$HOME/Documents/dev/toolbox/bin:$PATH"
```

## Tools

| Tool | Description |
|------|-------------|
| [bcat](bcat/) | Pipe stdin to a browser, infers filetype |
| [blinks](blinks/) | Find broken symlinks |
| [check-math](check-math/) | Verify math rendering in HTML/Markdown |
| [claude2md](claude2md/) | Convert claude.ai chat HTML to Markdown |
| [commit-survey](commit-survey/) | Survey a repo's commit and branch conventions |
| [gemini2md](gemini2md/) | Convert Gemini HTML exports to Markdown |
| [ips](ips/) | Show local and public IP addresses |
| [reflow](reflow/) | Reflow Markdown text preserving code blocks |
| [toks](toks/) | Count tokens (tiktoken) |
| [trunk](trunk/) | Print the repo's default branch |
| [webshot](webshot/) | Screenshot URLs and extract page metadata |

Most tools are [PEP 723](https://peps.python.org/pep-0723/) scripts that run via `uv run --script` -- no install step, dependencies are declared inline.

`bin/recorder` is a compatibility link to the standalone
[`parloq`](../parloq/) repo.

## Tests

```sh
tests/run.sh                   # core + uv-backed tools
TOOLBOX_BROWSER=1 tests/run.sh # also exercise webshot + check-math
```

CI ([`.github/workflows/ci.yml`](.github/workflows/ci.yml)) runs shellcheck, ruff
(`ruff.toml`), and the test suite on Linux and macOS, plus a browser job for the
Playwright-backed tools.
