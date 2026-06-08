# reflow

Reflow Markdown prose to a target column width, preserving code blocks and structure.

Word-wraps plain paragraphs to the target width. YAML front matter, fenced code
blocks, headings, list items, blockquotes, tables, thematic breaks, indented
blocks, and blank lines (paragraph breaks) pass through untouched. Long words and
URLs are never broken. Output goes to stdout.

## Usage

```sh
reflow document.md
cat document.md | reflow
reflow document.md --col-width 72
reflow document.md -w 72
```
