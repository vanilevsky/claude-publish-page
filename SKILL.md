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
3. **Run the uploader.** By default it **updates in place** at a stable URL:
   ```bash
   python3 ${CLAUDE_SKILL_DIR}/upload.py /tmp/<name>.html
   ```
   For a folder: `python3 ${CLAUDE_SKILL_DIR}/upload.py /tmp/<folder>`
   For a brand-new, non-overwriting URL (a genuinely different document, or a
   snapshot of the current version): add `--new`. Force a slug with
   `--slug photo-app`.
4. **Return the printed URL** to the user. The script prints exactly one line on
   stdout — the public URL — on success. When it overwrites an existing page it
   also prints a short heads-up to stderr; that's informational, the URL is still
   the line you return.

Still create the normal inline artifact too; the published URL is an addition,
not a replacement. Only skip publishing if the user says not to.

## Updating a page — same document → same URL

**Same document → same URL. Different document → new URL.** When you iterate on a
page — fix a typo, extend it, restyle the *same* document — just re-publish it.
Same title ⇒ same slug ⇒ same `<slug>.html`, so the existing link updates in
place and you can hand back the URL the user already has. For a *genuinely
different* document, give it a different title (or `--slug`) so it lands on its
own URL.

Overwriting replaces the previous content — there's no version history. To keep
the current version as a snapshot before a big change (or when unsure whether it
counts as "the same" document), publish with `--new` to mint a fresh,
non-overwriting URL instead of clobbering the old one.

## URL scheme

By default the key is a **stable** `<slug>.html`, where the slug comes from the
page `<title>` (Cyrillic is transliterated) or the filename. Re-publishing the
same document (same title ⇒ same slug) overwrites that key, so the URL stays put
and just shows the latest — this is what lets a living document keep one link.
Stable pages are uploaded with `Cache-Control: no-cache`, so a revisit always
revalidates and shows the update rather than a stale copy.

Pass `--new` to force a fresh, non-overwriting URL instead:
`<slug>-<random6>.html`. Use it for a genuinely separate document, or to snapshot
the current version before editing a page in place. These URLs are immutable and
hard to guess. `--slug my-page` sets the slug explicitly; combine it with `--new`
for a one-off immutable copy.

## First-time setup

`setup.py` configures any S3-compatible provider and writes a gitignored config
to `${CLAUDE_CONFIG_DIR:-~/.claude}/skill-data/publish-page/config.env` (mode
600). For Cloudflare R2 with a logged-in `wrangler` it can create the bucket and
enable the public `r2.dev` URL for you; for other providers you supply the
endpoint, bucket, public base URL and keys. See `config.example.env`.

## Notes

- `Content-Type` is set automatically (e.g. `text/html; charset=utf-8`) so pages
  render in the browser instead of downloading.
- **Cache caveat.** On Cloudflare `r2.dev` cache control is limited, so even with
  `no-cache` an updated stable page can occasionally look stale. If that happens,
  hard-refresh, or append a cache-buster like `?v=2` when sharing. A custom domain
  with Cache Rules is the robust fix for heavily-updated pages.
- **Updating a multi-file site** overwrites files in place but does not delete
  files removed since the last publish — old assets may linger under the prefix
  (usually harmless). Use `--new` for a clean slate.
- Pages are **public** — anyone with the link can view them. Don't publish
  sensitive content.
- `${CLAUDE_SKILL_DIR}` is the directory containing this file.
