#!/usr/bin/env python3
"""Publish an HTML page (or a folder of static files) to S3-compatible storage
and print its public URL.

Works with any S3-compatible provider (Cloudflare R2, AWS S3, MinIO, Backblaze
B2, DigitalOcean Spaces, Wasabi, …) — the endpoint/bucket/credentials come from
config, not from this file. Run setup.py once to create the config.

Usage:
    python3 upload.py PATH [--slug SLUG] [--new]

  PATH      A single .html file, or a directory containing static assets with
            an index.html at its root.
  --slug    Optional human-readable slug for the URL. If omitted, it is derived
            from the page's <title> (or the filename), transliterated to latin.
  --new     Force a fresh, non-overwriting URL (random suffix). Use for a
            genuinely different document, or to snapshot the current version
            before changing a page in place.

Default behaviour is to UPDATE IN PLACE: the object key is the stable
"<slug>[.html | /...]", so re-publishing the same document (same title -> same
slug) overwrites it and the URL stays the same. Stable pages are sent with
Cache-Control: no-cache so a revisit always revalidates and shows the latest.
With --new the key becomes "<slug>-<random-suffix>..." for a fresh, immutable
URL that never clobbers anything.
"""

import argparse
import mimetypes
import os
import re
import secrets
import sys

import _config

# Stable pages must always show the latest -> revalidate every load (the store
# sets an ETag, so unchanged content costs only a cheap 304). Fresh --new URLs
# are unique by construction, so they can be cached hard.
STABLE_CACHE    = "no-cache"
IMMUTABLE_CACHE = "public, max-age=31536000, immutable"

# Minimal Cyrillic -> Latin transliteration for clean slugs.
_CYR = {
    'а': 'a', 'б': 'b', 'в': 'v', 'г': 'g', 'д': 'd', 'е': 'e', 'ё': 'e', 'ж': 'zh', 'з': 'z',
    'и': 'i', 'й': 'y', 'к': 'k', 'л': 'l', 'м': 'm', 'н': 'n', 'о': 'o', 'п': 'p', 'р': 'r',
    'с': 's', 'т': 't', 'у': 'u', 'ф': 'f', 'х': 'h', 'ц': 'ts', 'ч': 'ch', 'ш': 'sh', 'щ': 'sch',
    'ъ': '', 'ы': 'y', 'ь': '', 'э': 'e', 'ю': 'yu', 'я': 'ya',
}


def slugify(text: str) -> str:
    text = (text or "").strip().lower()
    text = "".join(_CYR.get(ch, ch) for ch in text)
    text = re.sub(r"[^a-z0-9]+", "-", text).strip("-")
    return text[:60] or "page"


def title_from_html(path: str) -> str:
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            head = f.read(8192)
        m = re.search(r"<title[^>]*>(.*?)</title>", head, re.I | re.S)
        if m:
            return re.sub(r"\s+", " ", m.group(1)).strip()
    except OSError:
        pass
    return ""


def content_type_for(path: str) -> str:
    ctype, _ = mimetypes.guess_type(path)
    if ctype is None:
        ctype = "application/octet-stream"
    if ctype.startswith("text/") or ctype in ("application/javascript", "application/json"):
        ctype += "; charset=utf-8"
    return ctype


def make_client(cfg: dict):
    try:
        import boto3
        from botocore.config import Config
    except ImportError:
        sys.exit("boto3 is not installed. Run: pip install boto3 --break-system-packages -q")
    return boto3.client(
        "s3",
        endpoint_url=cfg.get("S3_ENDPOINT") or None,
        region_name=cfg.get("S3_REGION") or "auto",
        aws_access_key_id=cfg["S3_ACCESS_KEY_ID"],
        aws_secret_access_key=cfg["S3_SECRET_ACCESS_KEY"],
        config=Config(signature_version="s3v4"),
    )


def s3_put(client, bucket: str, key: str, path: str, cache_control: str):
    with open(path, "rb") as f:
        client.put_object(Bucket=bucket, Key=key, Body=f.read(),
                          ContentType=content_type_for(path),
                          CacheControl=cache_control)


def key_exists(client, bucket: str, key: str) -> bool:
    from botocore.exceptions import ClientError
    try:
        client.head_object(Bucket=bucket, Key=key)
        return True
    except ClientError:
        return False


def resolve_config() -> dict:
    """Load config or exit with an actionable message. Also respects the gate."""
    state = _config.load_state()
    if state.get("onboarded") and not state.get("cloud_enabled"):
        sys.exit("Cloud publishing is disabled for this skill. "
                 f"Run: python3 {os.path.join(os.path.dirname(__file__), 'setup.py')}")
    cfg = _config.load_config()
    missing = _config.missing_required(cfg)
    if missing:
        sys.exit("Missing config: " + ", ".join(missing) + ".\n"
                 f"Run: python3 {os.path.join(os.path.dirname(__file__), 'setup.py')}")
    return cfg


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("path", help="HTML file or directory to publish")
    ap.add_argument("--slug", default=None, help="Optional URL slug")
    ap.add_argument("--new", action="store_true",
                    help="Force a fresh, non-overwriting URL (random suffix). "
                         "Use for a different document, or to snapshot the "
                         "current version before editing a page in place.")
    args = ap.parse_args()

    path = os.path.abspath(args.path)
    if not os.path.exists(path):
        sys.exit(f"Not found: {path}")

    cfg = resolve_config()
    client = make_client(cfg)
    bucket = cfg["S3_BUCKET"]
    base = cfg["S3_PUBLIC_BASE"].rstrip("/")
    cache  = IMMUTABLE_CACHE if args.new else STABLE_CACHE
    suffix = f"-{secrets.token_hex(3)}" if args.new else ""  # 6 hex chars

    if os.path.isfile(path):
        slug = slugify(args.slug or title_from_html(path) or
                       os.path.splitext(os.path.basename(path))[0])
        key = f"{slug}{suffix}.html"
        if not args.new and key_exists(client, bucket, key):
            print(f"note: updating existing page at {key} "
                  f"(previous version overwritten; pass --new to keep it)",
                  file=sys.stderr)
        s3_put(client, bucket, key, path, cache)
        print(f"{base}/{key}")
        return

    # Directory: require an index.html, upload everything under a prefix.
    index = os.path.join(path, "index.html")
    if not os.path.isfile(index):
        sys.exit("Directory has no index.html at its root.")
    slug = slugify(args.slug or title_from_html(index) or os.path.basename(path))
    prefix = f"{slug}{suffix}"
    if not args.new and key_exists(client, bucket, f"{prefix}/index.html"):
        print(f"note: updating existing site at {prefix}/ (files overwritten in "
              f"place; files removed since last publish may linger under the "
              f"prefix; pass --new for a fresh URL)", file=sys.stderr)
    for root, _dirs, files in os.walk(path):
        for name in files:
            fp = os.path.join(root, name)
            rel = os.path.relpath(fp, path).replace(os.sep, "/")
            s3_put(client, bucket, f"{prefix}/{rel}", fp, cache)
    print(f"{base}/{prefix}/index.html")


if __name__ == "__main__":
    main()
