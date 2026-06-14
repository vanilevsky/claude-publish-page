---
name: publish-page
description: >-
  Publishes an HTML page to your own S3-compatible bucket (Cloudflare R2, AWS S3,
  MinIO, Backblaze B2, DigitalOcean Spaces, Wasabi, …) and returns a public,
  shareable URL. Use this whenever you create an HTML page, artifact, mini-app,
  dashboard, landing page, or any standalone .html deliverable and a link to open
  or share it would be useful — even without an explicit "publish" request. Also
  triggers on explicit asks like "publish this", "put it online", "make it
  shareable", "залей", "опубликуй", "дай ссылку". On first use it runs a one-time
  setup; if cloud publishing is turned off it just builds the page locally.
allowed-tools:
  - Bash
---

# Publish Page

Uploads an HTML page (or a folder of static files) to an S3-compatible bucket and
gives back a public URL. Configuration and credentials live outside this skill
(see "First-time setup"), so the skill itself contains no secrets.

## Gate — is cloud publishing enabled?

!`python3 ${CLAUDE_SKILL_DIR}/state.py status`

Act on the `STATUS=` line above:

- **`STATUS=not-onboarded`** — first use. Ask the user with **AskUserQuestion**:
  *"Publish built HTML pages to the cloud (S3 / Cloudflare R2) so you get a
  shareable link?"* — options **Yes** / **No, keep them local**.
  - **No** → run `python3 ${CLAUDE_SKILL_DIR}/state.py set-cloud false`. From now
    on just build HTML locally and hand back the file; do not publish.
  - **Yes** → run `python3 ${CLAUDE_SKILL_DIR}/setup.py` and walk the user through
    setup (it is interactive). When it finishes, continue with publishing.
- **`STATUS=cloud-disabled`** — do **not** upload. Produce the HTML artifact
  locally and return the file path. (If the user now explicitly asks to publish
  or enable cloud, run `python3 ${CLAUDE_SKILL_DIR}/setup.py`.)
- **`STATUS=cloud-enabled …`** — publish (see below) and return the URL.

## How to publish (when cloud is enabled)

1. **Make sure boto3 is available** (sandboxes reset between sessions):
   ```bash
   python3 -c "import boto3" 2>/dev/null || pip install boto3 --break-system-packages -q
   ```
2. **Write the page to a file**, e.g. `/tmp/<name>.html`. For a multi-file site,
   put everything in a folder with an `index.html` at its root.
3. **Run the uploader:**
   ```bash
   python3 ${CLAUDE_SKILL_DIR}/upload.py /tmp/<name>.html
   ```
   For a folder: `python3 ${CLAUDE_SKILL_DIR}/upload.py /tmp/<folder>`
   Optionally force a slug: `--slug photo-app`
4. **Return the printed URL** to the user. The script prints exactly one line —
   the public URL — on success.

Still create the normal inline artifact too; the published URL is an addition,
not a replacement. Only skip publishing if the user says not to.

## URL scheme

Keys are `<slug>-<random6>.html`, where the slug comes from the page `<title>`
(Cyrillic is transliterated) or the filename. The random suffix makes every
publish a fresh, non-overwriting, hard-to-guess URL.

## First-time setup

`setup.py` configures any S3-compatible provider and writes a gitignored config
to `${CLAUDE_CONFIG_DIR:-~/.claude}/skill-data/publish-page/config.env` (mode
600). For Cloudflare R2 with a logged-in `wrangler` it can create the bucket and
enable the public `r2.dev` URL for you; for other providers you supply the
endpoint, bucket, public base URL and keys. See `config.example.env`.

## Notes

- `Content-Type` is set automatically (e.g. `text/html; charset=utf-8`) so pages
  render in the browser instead of downloading.
- Pages are **public** — anyone with the link can view them. Don't publish
  sensitive content.
- `${CLAUDE_SKILL_DIR}` is the directory containing this file.
