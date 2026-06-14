#!/usr/bin/env python3
"""Gate state for the publish-page skill: is cloud publishing enabled?

Usage:
    python3 state.py status            # prints STATUS=... (used by SKILL.md gate)
    python3 state.py set-cloud true    # enable  (also marks onboarded)
    python3 state.py set-cloud false   # disable (also marks onboarded)

`status` prints exactly one line and always exits 0 so it is safe to embed in a
SKILL.md `!`-injection:
    STATUS=not-onboarded
    STATUS=cloud-disabled
    STATUS=cloud-enabled bucket=<bucket> base=<public-base>
"""

import sys

import _config


def cmd_status() -> int:
    state = _config.load_state()
    if not state.get("onboarded"):
        print("STATUS=not-onboarded")
        return 0
    if not state.get("cloud_enabled"):
        print("STATUS=cloud-disabled")
        return 0
    cfg = _config.load_config()
    print(f"STATUS=cloud-enabled bucket={cfg.get('S3_BUCKET', '')} "
          f"base={cfg.get('S3_PUBLIC_BASE', '')}")
    return 0


def cmd_set_cloud(value: str) -> int:
    enabled = value.strip().lower() in ("true", "1", "yes", "on", "y")
    state = _config.load_state()
    state["onboarded"] = True
    state["cloud_enabled"] = enabled
    path = _config.save_state(state)
    print(f"cloud_enabled={'true' if enabled else 'false'} ({path})")
    return 0


def main() -> int:
    args = sys.argv[1:]
    if not args or args[0] == "status":
        return cmd_status()
    if args[0] == "set-cloud" and len(args) == 2:
        return cmd_set_cloud(args[1])
    sys.stderr.write(
        "Usage:\n"
        "  python3 state.py status\n"
        "  python3 state.py set-cloud true|false\n"
    )
    return 2


if __name__ == "__main__":
    sys.exit(main())
