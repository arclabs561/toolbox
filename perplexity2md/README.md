# perplexity2md

Convert Perplexity conversation HTML to Markdown.

## Usage

```sh
pbpaste | perplexity2md              # clipboard to stdout
pbpaste | perplexity2md -o convo.md  # clipboard to file
perplexity2md saved.html             # file arg
perplexity2md saved.html -o out.md   # file to file
```

Copy the page DOM first: devtools, right-click the `<html>` element, Copy > Copy outerHTML.

Each query and its answer become a `## User` / `## Perplexity` pair. Inline status
steps are folded into the answer; collapsible subagent panels are dropped. Citation
chips become markdown links and KaTeX math is emitted as its TeX source.

For newer Perplexity task pages that do not expose a user turn, the tool falls back to
the `<main>` content, starts at the first answer heading, strips page chrome, and emits
the answer as standalone Markdown.

If a captured DOM only contains an assistant answer block, the tool emits that answer
directly instead of adding a synthetic `## Perplexity` wrapper.
