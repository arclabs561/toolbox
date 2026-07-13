# chatgpt2md

Convert ChatGPT conversation HTML to Markdown.

## Usage

```sh
pbpaste | chatgpt2md              # clipboard to stdout
pbpaste | chatgpt2md -o convo.md  # clipboard to file
chatgpt2md saved.html             # file arg
chatgpt2md saved.html -o out.md   # file to file
```

Copy the page DOM first: in browser developer tools, right-click the `<html>`
element, then select Copy > Copy outerHTML.
