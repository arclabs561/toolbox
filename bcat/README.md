# bcat

Pipe stdin to a browser. Infers filetype from content or `-t` flag.

## Usage

```sh
echo '<h1>hi</h1>' | bcat
cat data.json | bcat -t json
cat README.md | bcat -t md
bcat < style.css
```
