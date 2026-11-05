#!/usr/bin/env python3
"""Determine which Flatpak apps under apps/ need to be built and published."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
APPS_DIR = REPO_ROOT / "apps"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--published-apps-json",
        type=Path,
        help="Path to apps.json from the existing gh-pages branch.",
    )
    parser.add_argument(
        "--force-app",
        default="",
        help="Force build a specific app ID (or 'all' for all apps).",
    )
    args = parser.parse_args()

    published: dict[str, dict[str, str]] = {}
    if args.published_apps_json and args.published_apps_json.exists():
        try:
            published = json.loads(args.published_apps_json.read_text(encoding="utf-8"))
        except Exception as exc:
            print(f"Warning: could not parse {args.published_apps_json}: {exc}")

    to_build: list[dict[str, str]] = []
    for app_dir in sorted(APPS_DIR.iterdir()):
        if not app_dir.is_dir():
            continue
        app_id = app_dir.name
        version_file = app_dir / "VERSION"
        version = (
            version_file.read_text(encoding="utf-8").strip()
            if version_file.exists()
            else "latest"
        )
        pub_version = published.get(app_id, {}).get("version")

        force = args.force_app in ("all", "*", app_id)
        if force or pub_version != version:
            print(
                f"[BUILD NEEDED] {app_id}: repo version={version}, published version={pub_version} (force={force})"
            )
            to_build.append({"app_id": app_id, "version": version})
        else:
            print(f"[UP TO DATE]   {app_id}: version={version}")

    should_build = len(to_build) > 0
    github_output = os.environ.get("GITHUB_OUTPUT")
    if github_output:
        with open(github_output, "a", encoding="utf-8") as f:
            f.write(f"should_build={'true' if should_build else 'false'}\n")
            f.write(f"apps={json.dumps(to_build)}\n")


if __name__ == "__main__":
    main()
