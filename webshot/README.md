# webshot

Screenshot URLs or local HTML files and extract page metadata. Headless Chromium via Playwright.

## Usage

```sh
webshot shot https://example.com
webshot shot page.html -o page.png
webshot shot https://example.com --full-page --width 1280
webshot shot https://example.com --selector "article"
webshot shot https://example.com --mobile --dark
webshot shot https://example.com --jpg --quality 80
cat page.html | webshot shot - -o out.png

webshot meta https://example.com
webshot meta https://example.com --json
webshot meta page.html --all --json
```

### shot flags

`-o`, `--width`, `--height`, `--scale`, `--full-page`, `--dark`, `--mobile`, `--selector`, `--jpg`, `--quality`, `--wait`, `--timeout`

### meta output

Title, description, Open Graph, Twitter Card, canonical URL, headings, JSON-LD. Noisy meta tags (analytics, tracking) are filtered by default; `--all` includes everything.

## Dependencies

Playwright (`uv run --script` handles installation). First run installs Chromium: `uv run playwright install chromium`.
