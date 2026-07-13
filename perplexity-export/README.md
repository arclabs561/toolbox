# perplexity-export

Explore and export Perplexity chats through the web UI.

## Usage

```sh
perplexity-export auth
perplexity-export verify
perplexity-export explore
perplexity-export explore --interactive
perplexity-export ask "compare these two notes" --export
perplexity-export export --interactive
perplexity-export export https://www.perplexity.ai/search/...
perplexity-export stop
```

`auth` opens a visible Chromium profile and tries to prefill a 1Password item named
`Perplexity` (`PERPLEXITY_OP_ITEM` overrides it). Complete any SSO, one-time code, or
passkey step manually, then press Enter in the terminal. The profile is stored outside
the repo under the XDG data directory. Set `OP_CONFIG_DIR` if the 1Password CLI must
use a non-default configuration directory.

`verify` probes the same profile headlessly and reports whether Perplexity or
Cloudflare security verification is blocking access. It will not open a window unless
you explicitly pass `--headed`.

## Security Verification

If Perplexity or Cloudflare asks for verification, run:

```sh
perplexity-export verify --headed
```

Complete the verification in the visible Playwright browser, press Enter in the
terminal, then retry `ask`, `explore`, or `export`. The tool keeps using the same
persistent profile. It does not use CAPTCHA-solving packages or click challenges in
headless mode.

`explore`, `ask`, and `export` auto-start a headless Playwright browser in the
background with that same persistent profile. They reuse it through a local Unix socket
until the idle TTL expires or `stop` is run. `start --ttl 45m` is only needed when you
want to prewarm the session explicitly.

Exports include:

- `page.html`, the rendered DOM snapshot.
- `page.md`, converted with `perplexity2md` when available.
- `screenshot.png`.
- `metadata.json`.
- `assets/`, containing rendered-page media and stylesheet assets fetched with page
  credentials where the browser can access them.

Asset export is best-effort. The tool saves assets exposed in the rendered page; it
cannot reconstruct private CDN data that the page does not reference.
