# toolbox

Single-file CLI tools. Each lives in its own directory; `bin/` has symlinks for PATH.

## Setup

```sh
# add to your shell profile
export PATH="$HOME/Documents/dev/toolbox/bin:$PATH"
```

## Tools

| Tool | Description |
|------|-------------|
| [bcat](bcat/) | Pipe stdin to a browser, infers filetype |
| [check-math](check-math/) | Verify math rendering in HTML/Markdown |
| [gemini2md](gemini2md/) | Convert Gemini HTML exports to Markdown |
| [ips](ips/) | Show local and public IP addresses |
| [toks](toks/) | Count tokens (tiktoken) |
| [webshot](webshot/) | Screenshot URLs and extract page metadata |

Most tools are [PEP 723](https://peps.python.org/pep-0723/) scripts that run via `uv run --script` -- no install step, dependencies are declared inline.
