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
| [pinglet](pinglet/) | Show local/public IPs and run network diagnostics (`pingl` shortcut) |
| [perplexity-export](perplexity-export/) | Explore and export Perplexity chats |
| [perplexity2md](perplexity2md/) | Convert Perplexity chat HTML to Markdown |
| [reflow](reflow/) | Reflow Markdown text preserving code blocks |
| [toks](toks/) | Count tokens (tiktoken) |
| [trunk](trunk/) | Print the repo's default branch |
| [webshot](webshot/) | Screenshot URLs and extract page metadata |

Most tools are [PEP 723](https://peps.python.org/pep-0723/) scripts that run via `uv run --script` -- no install step, dependencies are declared inline.

`bin/recorder` is a compatibility link to the standalone
[`parloq`](../parloq/) repo.

## Tests

```sh
just test                       # core + uv-backed tools
TOOLBOX_BROWSER=1 tests/run.sh # also exercise webshot + check-math
```

`just docker-base` builds the toolbox-owned Linux dependency image from the
official Python slim image. It installs only the network tools and Python
dependencies needed by `pinglet`, then runs as a non-root user. `just
test-docker` uses that local base in a `--network none` container by default:

```sh
just docker-base
just test-docker
```

To publish a multi-architecture base image to GitHub Container Registry,
refresh GitHub CLI with package-write permission, then run:

```sh
gh auth refresh --hostname github.com --scopes write:packages
just docker-base-push
```

The push target defaults to
`ghcr.io/arclabs561/toolbox-pinglet-base:python3.12`. Override
`TOOLBOX_BASE_IMAGE` or `TOOLBOX_DOCKER_PLATFORMS` when needed. Use
`TOOLBOX_DOCKER_BASE` to smoke-test a registry tag or another already available
image.

For a bounded local matrix, provide only images and platforms already available
to the active context:

```sh
TOOLBOX_DOCKER_BASES='toolbox-pinglet-base:python3.12' \
TOOLBOX_DOCKER_PLATFORMS='linux/arm64' \
just test-docker-matrix
```

The matrix does not pull images implicitly. A platform that is not supported by
the selected base image fails as a normal container-test failure.

CI ([`.github/workflows/ci.yml`](.github/workflows/ci.yml)) runs shellcheck, ruff
(`ruff.toml`), and the test suite on Linux and macOS, plus a browser job for the
Playwright-backed tools.

## License

Licensed under either the [Apache License, Version 2.0](LICENSE-APACHE) or
the [MIT license](LICENSE-MIT), at your option.
