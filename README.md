# claude-publish-page

A [Claude Code](https://claude.com/claude-code) **Skill** that publishes the HTML
pages Claude builds for you to your own bucket and hands back a public, shareable
link — so you can open them on your phone or send them to someone.

Works with **any S3-compatible storage**: Cloudflare R2, AWS S3, MinIO, Backblaze
B2, DigitalOcean Spaces, Wasabi, GCS (S3-interop), … The skill ships **no
credentials** — you point it at your own bucket during a one-time setup.

## How it works

- Claude builds an `.html` page (or a folder with `index.html`).
- The skill uploads it under a fresh `slug-<random>.html` key (sets the right
  `Content-Type`, so it renders instead of downloading).
- You get back a public URL like `https://pub-….r2.dev/my-page-a1b2c3.html`.

A one-time **opt-in gate** controls all of this: on first use the skill asks
whether you want cloud publishing at all. If you say no, it simply builds HTML
locally and never uploads anything.

## Requirements

- Python 3 with **boto3** (`pip install boto3 --break-system-packages -q`).
- An S3-compatible bucket you control.
- *Optional:* [`wrangler`](https://developers.cloudflare.com/workers/wrangler/)
  for the Cloudflare R2 fast-path (auto-create bucket + enable the public URL).

## Install

Copy the skill into your Claude Code skills directory:

```bash
git clone https://github.com/vanilevsky/claude-publish-page.git
cp -r claude-publish-page ~/.claude/skills/publish-page
```

(or symlink it). Then run the one-time setup:

```bash
python3 ~/.claude/skills/publish-page/setup.py
```

`setup.py` is interactive. For Cloudflare R2 with a logged-in `wrangler` it can
create the bucket and turn on its public `r2.dev` URL for you; for other
providers you supply the endpoint, bucket, public base URL and keys. See
[`config.example.env`](config.example.env) for every value.

## Where config and state live

Nothing secret is stored inside the skill/repo. Setup writes to:

```
${CLAUDE_CONFIG_DIR:-~/.claude}/skill-data/publish-page/
├── config.env    # endpoint, bucket, public base, S3 keys   (mode 600)
└── state.json    # { "onboarded": bool, "cloud_enabled": bool }
```

Every config value can also be provided as an environment variable (handy for
sandboxes/CI), which overrides the file.

## Usage

You normally don't call anything — Claude invokes the skill automatically after
building an HTML page. Under the hood:

```bash
python3 ~/.claude/skills/publish-page/upload.py page.html          # single file
python3 ~/.claude/skills/publish-page/upload.py ./site/            # folder w/ index.html
python3 ~/.claude/skills/publish-page/upload.py page.html --slug report
```

It prints exactly one line on success: the public URL.

To toggle cloud publishing later:

```bash
python3 ~/.claude/skills/publish-page/state.py set-cloud true|false
```

## ⚠️ Pages are public

Anyone with the link can view a published page. Don't publish anything sensitive.

## License

[MIT](LICENSE)
