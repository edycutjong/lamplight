# CHANGELOG


## v1.1.0 (2026-07-18)

### Bug Fixes

- Audit fixes — 458 test count, self-contained ARCHITECTURE doc, queue label in support example,
  edycutjong GitHub handle
  ([`f83cb92`](https://github.com/edycutjong/lamplight/commit/f83cb9231f7a9092793a759f6f88022bbdaaaa02))

- **assets**: Og-image chip LIVE→BUILT ON QWEN CLOUD (honest pre-deploy)
  ([`a7ef475`](https://github.com/edycutjong/lamplight/commit/a7ef475a3ea03b595cad742f4d50bacc761e3ffe))

### Continuous Integration

- Add Stage 6 semantic-release to pipeline + versioning docs
  ([`0782e0e`](https://github.com/edycutjong/lamplight/commit/0782e0ea53201512a87cb8ae457eb7658a6b400d))

### Features

- Landing page + 10-slide pitch deck + GitHub Pages deploy at lamplight.edycu.dev
  ([`f1fe31e`](https://github.com/edycutjong/lamplight/commit/f1fe31e8fb8c439aa7ecfe010fc4c781ff5a0b77))

- site/index.html: warm lamplit editorial landing (Fraunces/Karla), real receipts count-up (458
  tests, 100% cov, 334/2000 tok, 0.99 vs 0.85 recall, 0 vs 151 resurfaced), cefazolin-thread brief
  recreation with [s04][s06][s12] citation chips + strikethrough retired item, honest-by-design
  disclosures, FAQ - site/pitch/index.html: 10 slides, 1920x1080 scaled stage, keys arrows/space/
  ESC-overview/P-presenter/C-contrast, @page 16in 9in print, speaker notes, doc-quality SVG
  architecture slide, shipped-facts-only traction - site/: icon.svg, og-image.png, readme-hero.png,
  apple-touch-icon.png (180x180), CNAME lamplight.edycu.dev; full OG/twitter metadata on both pages
  - .github/workflows/pages.yml: Deploy Pages (configure-pages@v5 -> upload-pages-artifact@v3
  path:site -> deploy-pages@v4) - README.md: Live + Pitch Deck badges


## v1.0.0 (2026-07-14)

### Features

- Initial import of lamplight-memory
  ([`a6b64cb`](https://github.com/edycutjong/lamplight/commit/a6b64cb9ac233476b0e65724a37048297607fb44))
