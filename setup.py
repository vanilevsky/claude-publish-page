#!/usr/bin/env python3
"""One-time onboarding for the publish-page skill (public mode).

Configures an S3-compatible bucket and writes the (gitignored) config + state to
${CLAUDE_CONFIG_DIR:-~/.claude}/skill-data/publish-page/.

Two paths:
  * Cloudflare R2 fast-path — if you pick R2 and have `wrangler` logged in, this
    can create the bucket and enable its public r2.dev URL for you.
  * Generic S3 — for AWS S3, MinIO, Backblaze B2, DO Spaces, Wasabi, etc. you
    provide endpoint / bucket / public base / keys (public exposure is yours to
    configure on the provider side).

Interactive by default; every value can also be supplied via a flag, and the two
secrets may come from the environment (S3_ACCESS_KEY_ID / S3_SECRET_ACCESS_KEY)
so they never appear in your shell history or the process list.

Examples:
    python3 setup.py                                   # fully interactive
    python3 setup.py --provider r2 --bucket my-pages   # R2 fast-path
    S3_ACCESS_KEY_ID=… S3_SECRET_ACCESS_KEY=… \\
      python3 setup.py --provider other --non-interactive \\
      --endpoint https://… --bucket b --public-base https://cdn.example.com
"""

import argparse
import os
import re
import shutil
import subprocess
import sys

import _config

ACCOUNT_RE = re.compile(r"\b[0-9a-f]{32}\b")
DEVURL_RE = re.compile(r"https://pub-[0-9a-f]+\.r2\.dev", re.I)


def ask(prompt: str, default: str = "", secret: bool = False, non_interactive: bool = False) -> str:
    if non_interactive:
        return default
    suffix = f" [{default}]" if default else ""
    if secret:
        import getpass
        val = getpass.getpass(f"{prompt}{suffix}: ")
    else:
        val = input(f"{prompt}{suffix}: ").strip()
    return val or default


def run(cmd: list) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True)


def ensure_boto3() -> None:
    try:
        import boto3  # noqa: F401
    except ImportError:
        print("boto3 is required. Install it with:\n"
              "  pip install boto3 --break-system-packages -q")
        sys.exit(1)


def wrangler_authenticated() -> bool:
    """True only if wrangler has usable credentials (cached login or token).

    Without auth, `wrangler r2 ...` runs as "non-interactive" and errors asking
    for CLOUDFLARE_API_TOKEN, so the R2 fast-path must be skipped gracefully.
    """
    if not shutil.which("wrangler"):
        return False
    if os.environ.get("CLOUDFLARE_API_TOKEN"):
        return True
    res = run(["wrangler", "whoami"])
    out = (res.stdout + res.stderr).lower()
    return res.returncode == 0 and "not authenticated" not in out


def wrangler_account_id() -> str:
    if not wrangler_authenticated():
        return ""
    res = run(["wrangler", "whoami"])
    ids = ACCOUNT_RE.findall(res.stdout or "")
    return ids[0] if len(set(ids)) == 1 else ""


def r2_create_bucket(bucket: str) -> None:
    res = run(["wrangler", "r2", "bucket", "create", bucket])
    out = (res.stdout + res.stderr).lower()
    if res.returncode == 0:
        print(f"  ✓ bucket '{bucket}' created")
    elif "already" in out or "exists" in out:
        print(f"  ✓ bucket '{bucket}' already exists")
    else:
        print(f"  ! could not create bucket via wrangler:\n{res.stderr.strip()}")


def r2_enable_devurl(bucket: str) -> str:
    """Enable the public r2.dev URL and return it (best effort)."""
    for cmd in (["wrangler", "r2", "bucket", "dev-url", "enable", bucket],
                ["wrangler", "r2", "bucket", "dev-url", "get", bucket]):
        res = run(cmd)
        m = DEVURL_RE.search(res.stdout + res.stderr)
        if m:
            return m.group(0)
    return ""


def provider_menu(non_interactive: bool, default: str) -> str:
    if non_interactive:
        return default or "other"
    print("Which storage provider?")
    print("  1) Cloudflare R2 (fast-path: can create bucket + enable public URL)")
    print("  2) AWS S3")
    print("  3) Other S3-compatible (MinIO, B2, Spaces, Wasabi, …)")
    choice = input("Choose [1/2/3] (1): ").strip() or "1"
    return {"1": "r2", "2": "aws", "3": "other"}.get(choice, "r2")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--provider", choices=["r2", "aws", "other"])
    ap.add_argument("--bucket")
    ap.add_argument("--public-base")
    ap.add_argument("--endpoint")
    ap.add_argument("--region")
    ap.add_argument("--access-key-id")
    ap.add_argument("--secret-access-key")
    ap.add_argument("--create-bucket", action="store_true",
                    help="Attempt to create the bucket (R2 via wrangler, else boto3)")
    ap.add_argument("--non-interactive", action="store_true",
                    help="Never prompt; fail if a required value is missing")
    args = ap.parse_args()
    ni = args.non_interactive

    ensure_boto3()

    provider = args.provider or provider_menu(ni, "r2")
    cfg = {k: "" for k in _config.REQUIRED + _config.OPTIONAL}

    # --- credentials (env preferred so they stay out of argv/history) ---
    cfg["S3_ACCESS_KEY_ID"] = (
        os.environ.get("S3_ACCESS_KEY_ID") or args.access_key_id
        or ask("S3 Access Key ID", non_interactive=ni))
    cfg["S3_SECRET_ACCESS_KEY"] = (
        os.environ.get("S3_SECRET_ACCESS_KEY") or args.secret_access_key
        or ask("S3 Secret Access Key", secret=True, non_interactive=ni))

    cfg["S3_BUCKET"] = args.bucket or ask("Bucket name", non_interactive=ni)

    if provider == "r2":
        cfg["S3_REGION"] = args.region or "auto"
        account = wrangler_account_id() or ask(
            "Cloudflare account ID (32 hex)", non_interactive=ni)
        if args.endpoint:
            cfg["S3_ENDPOINT"] = args.endpoint
        elif account:
            cfg["S3_ENDPOINT"] = f"https://{account}.r2.cloudflarestorage.com"

        if cfg["S3_BUCKET"] and not ni:
            if wrangler_authenticated():
                print("R2 fast-path (wrangler):")
                r2_create_bucket(cfg["S3_BUCKET"])
                url = r2_enable_devurl(cfg["S3_BUCKET"])
                if url:
                    print(f"  ✓ public URL: {url}")
                    cfg["S3_PUBLIC_BASE"] = url
            elif shutil.which("wrangler"):
                print("wrangler is installed but not logged in — skipping R2 auto-create.")
                print("  Run `wrangler login` (or set CLOUDFLARE_API_TOKEN) and re-run to")
                print("  auto-create the bucket and enable its public r2.dev URL.")
        cfg["S3_PUBLIC_BASE"] = (
            args.public_base or cfg["S3_PUBLIC_BASE"]
            or ask("Public base URL (https://pub-….r2.dev)", non_interactive=ni))
    else:
        cfg["S3_ENDPOINT"] = (
            args.endpoint if args.endpoint is not None
            else ask("S3 endpoint URL (blank for AWS default)",
                     default="" if provider == "aws" else "", non_interactive=ni))
        cfg["S3_REGION"] = args.region or ask(
            "Region", default="us-east-1" if provider == "aws" else "auto",
            non_interactive=ni)
        cfg["S3_PUBLIC_BASE"] = args.public_base or ask(
            "Public base URL (where the bucket is served, no trailing slash)",
            non_interactive=ni)
        if args.create_bucket:
            _boto3_create_bucket(cfg)

    missing = _config.missing_required(cfg)
    if missing:
        sys.stderr.write("Missing required values: " + ", ".join(missing) + "\n")
        return 1

    path = _config.write_config(cfg)
    os.chmod(path, 0o600)
    _config.save_state({"onboarded": True, "cloud_enabled": True})

    print()
    print(f"✓ Config written: {path} (mode 600)")
    print(f"✓ Cloud publishing enabled for bucket '{cfg['S3_BUCKET']}'")
    print()
    print("Try it:")
    print("  echo '<h1>hi</h1>' > /tmp/hi.html")
    print(f"  python3 {os.path.join(os.path.dirname(os.path.abspath(__file__)), 'upload.py')} /tmp/hi.html")
    return 0


def _boto3_create_bucket(cfg: dict) -> None:
    import boto3
    from botocore.config import Config
    client = boto3.client(
        "s3", endpoint_url=cfg.get("S3_ENDPOINT") or None,
        region_name=cfg.get("S3_REGION") or "auto",
        aws_access_key_id=cfg["S3_ACCESS_KEY_ID"],
        aws_secret_access_key=cfg["S3_SECRET_ACCESS_KEY"],
        config=Config(signature_version="s3v4"))
    try:
        client.create_bucket(Bucket=cfg["S3_BUCKET"])
        print(f"  ✓ bucket '{cfg['S3_BUCKET']}' created")
    except Exception as exc:  # noqa: BLE001 — provider-specific "already exists" errors vary
        print(f"  ! create_bucket: {exc}")


if __name__ == "__main__":
    sys.exit(main())
