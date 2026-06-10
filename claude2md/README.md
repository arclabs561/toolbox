# claude2md

Convert claude.ai conversation HTML to Markdown.

## Usage

```sh
pbpaste | claude2md              # clipboard to stdout
pbpaste | claude2md -o convo.md  # clipboard to file
claude2md saved.html             # file arg
claude2md saved.html -o out.md   # file to file
```

Copy the page DOM first: devtools, right-click the `<html>` element, Copy > Copy outerHTML.
