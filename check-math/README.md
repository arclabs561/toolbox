# check-math

Verify LaTeX math rendering in Markdown files. Serves via go-grip (GitHub-accurate MathJax rendering), then checks for unrendered delimiters and parse errors in a headless browser.

## Prerequisites

```sh
go install github.com/chrishrb/go-grip@latest
```

## Usage

```sh
check-math document.md
check-math document.md -s screenshot.png
check-math **/*.md
```
