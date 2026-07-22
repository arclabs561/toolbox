# toolbox

Simple CLI tools. Each lives in its own directory; `bin/` has symlinks for PATH.

## Setup

```sh
just install       # validate tools and create bin/ links
eval "$(just path)" # or add the printed line to your shell profile
```

Tools are mostly PEP 723 scripts, so there is no separate runtime install or
compiled artifact. `just build` validates the scripts; `just test` runs the
integration suite.

## Tools

| Tool | Description |
|------|-------------|
| [bcat](bcat/) | Pipe stdin to a browser, infers filetype |
| [blinks](blinks/) | Find broken symlinks |
| [check-math](check-math/) | Verify math rendering in HTML/Markdown |
| [chatgpt2md](chatgpt2md/) | Convert ChatGPT chat HTML to Markdown |
| [claude2md](claude2md/) | Convert claude.ai chat HTML to Markdown |
| [commit-survey](commit-survey/) | Survey a repo's commit and branch conventions |
| [gemini2md](gemini2md/) | Convert Gemini HTML exports to Markdown |
| [gh-dependabot](gh-dependabot/) | Inventory open Dependabot alerts across public repositories |
| [perplexity-export](perplexity-export/) | Explore and export Perplexity chats |
| [perplexity2md](perplexity2md/) | Convert Perplexity chat HTML to Markdown |
| [reflow](reflow/) | Reflow Markdown text preserving code blocks |
| [toks](toks/) | Count tokens (tiktoken) |
| [trunk](trunk/) | Print the repo's default branch |
| [webshot](webshot/) | Screenshot URLs and extract page metadata |

Most tools are [PEP 723](https://peps.python.org/pep-0723/) scripts that run via `uv run --script` -- no install step, dependencies are declared inline.

`bin/recorder` is a compatibility link to the standalone
[`parloq`](../parloq/) repo.

The former `pinglet` network diagnostic now lives in the standalone Rust
[`linktop`](../linktop/) project. Its own `just install` installs `linktop` plus
the `pinglet` and `pingl` compatibility names into Cargo's bin directory.

## Tests

```sh
just test                       # core + uv-backed tools
TOOLBOX_BROWSER=1 tests/run.sh # also exercise webshot + check-math
```

CI ([`.github/workflows/ci.yml`](.github/workflows/ci.yml)) runs shellcheck, ruff
(`ruff.toml`), and the test suite on Linux and macOS, plus a browser job for the
Playwright-backed tools.

## License

Licensed under either the [Apache License, Version 2.0](LICENSE-APACHE) or
the [MIT license](LICENSE-MIT), at your option.
