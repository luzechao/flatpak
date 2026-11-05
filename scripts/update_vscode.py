#!/usr/bin/env python3
"""Track the latest microsoft/vscode release and update the Flatpak manifest."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import urllib.request


REPO_ROOT = Path(__file__).resolve().parent.parent
APP_DIR = REPO_ROOT / "apps" / "com.visualstudio.code"
MANIFEST_PATH = APP_DIR / "com.visualstudio.code.yaml"
METAINFO_PATH = APP_DIR / "com.visualstudio.code.metainfo.xml"
VERSION_PATH = APP_DIR / "VERSION"


class NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def get_latest_vscode_release() -> tuple[str, str]:
    url = "https://api.github.com/repos/microsoft/vscode/releases/latest"
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "luzechao-flatpak-updater",
    }
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"

    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read().decode("utf-8"))

    version = data["tag_name"].lstrip("v")
    published_at = data.get("published_at", "")[:10]
    return version, published_at


def get_deb_metadata(version: str, deb_arch: str) -> tuple[str, str, int]:
    update_url = f"https://update.code.visualstudio.com/{version}/linux-deb-{deb_arch}/stable"
    opener = urllib.request.build_opener(NoRedirectHandler)
    req = urllib.request.Request(
        update_url,
        method="HEAD",
        headers={"User-Agent": "luzechao-flatpak-updater"},
    )

    location = None
    sha256 = None
    try:
        with opener.open(req, timeout=30) as resp:
            headers = {k.lower(): v for k, v in resp.headers.items()}
            location = headers.get("location")
            sha256 = headers.get("x-sha256")
    except urllib.error.HTTPError as e:
        if e.code in (301, 302, 303, 307, 308):
            headers = {k.lower(): v for k, v in e.headers.items()}
            location = headers.get("location")
            sha256 = headers.get("x-sha256")
        else:
            raise

    size = None
    if location:
        head_req = urllib.request.Request(
            location,
            method="HEAD",
            headers={"User-Agent": "luzechao-flatpak-updater"},
        )
        with urllib.request.urlopen(head_req, timeout=30) as resp:
            cl = resp.headers.get("Content-Length")
            if cl is not None:
                size = int(cl)

    if not sha256 or size is None:
        dl_url = location or update_url
        dl_req = urllib.request.Request(
            dl_url, headers={"User-Agent": "luzechao-flatpak-updater"}
        )
        h = hashlib.sha256()
        total = 0
        with urllib.request.urlopen(dl_req, timeout=300) as resp:
            while True:
                chunk = resp.read(1024 * 1024)
                if not chunk:
                    break
                h.update(chunk)
                total += len(chunk)
        sha256 = h.hexdigest()
        size = total

    return update_url, sha256.lower(), size


def get_current_manifest_version(manifest_text: str) -> str | None:
    m = re.search(
        r"https://update\.code\.visualstudio\.com/([^/]+)/linux-deb-x64/stable",
        manifest_text,
    )
    return m.group(1) if m else None


def update_manifest(
    manifest_text: str,
    x64_meta: tuple[str, str, int],
    arm64_meta: tuple[str, str, int],
) -> str:
    x64_url, x64_sha256, x64_size = x64_meta
    arm64_url, arm64_sha256, arm64_size = arm64_meta

    pattern_x64 = re.compile(
        r"(only-arches:\s*\[x86_64\]\s*\n"
        r"\s*url:\s*)https://update\.code\.visualstudio\.com/[^\n]+\n"
        r"(\s*sha256:\s*)[0-9a-fA-F]+\n"
        r"(\s*size:\s*)\d+"
    )
    manifest_text, n_x64 = pattern_x64.subn(
        rf"\g<1>{x64_url}\n\g<2>{x64_sha256}\n\g<3>{x64_size}",
        manifest_text,
        count=1,
    )
    if n_x64 != 1:
        raise RuntimeError("Failed to locate x86_64 extra-data block in manifest")

    pattern_arm64 = re.compile(
        r"(only-arches:\s*\[aarch64\]\s*\n"
        r"\s*url:\s*)https://update\.code\.visualstudio\.com/[^\n]+\n"
        r"(\s*sha256:\s*)[0-9a-fA-F]+\n"
        r"(\s*size:\s*)\d+"
    )
    manifest_text, n_arm64 = pattern_arm64.subn(
        rf"\g<1>{arm64_url}\n\g<2>{arm64_sha256}\n\g<3>{arm64_size}",
        manifest_text,
        count=1,
    )
    if n_arm64 != 1:
        raise RuntimeError("Failed to locate aarch64 extra-data block in manifest")

    return manifest_text


def update_metainfo(metainfo_text: str, version: str, release_date: str) -> str:
    if f'version="{version}"' in metainfo_text:
        return metainfo_text

    metainfo_text = metainfo_text.replace(
        "<description></description>", "<description/>", 1
    )
    new_entry = (
        f"  <releases>\n"
        f'    <release version="{version}" date="{release_date}">\n'
        f"      <description></description>\n"
        f"    </release>"
    )
    if "  <releases>" not in metainfo_text:
        raise RuntimeError("Failed to find <releases> tag in metainfo.xml")
    return metainfo_text.replace("  <releases>", new_entry, 1)


def write_github_output(updated: bool, version: str, current_version: str | None) -> None:
    github_output = os.environ.get("GITHUB_OUTPUT")
    if not github_output:
        return
    with open(github_output, "a", encoding="utf-8") as f:
        f.write(f"updated={'true' if updated else 'false'}\n")
        f.write(f"version={version}\n")
        f.write(f"previous_version={current_version or ''}\n")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check-only",
        action="store_true",
        help="Only check for updates without modifying files.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Refresh hashes and sizes even if the version matches.",
    )
    args = parser.parse_args()

    manifest_text = MANIFEST_PATH.read_text(encoding="utf-8")
    current_version = get_current_manifest_version(manifest_text)
    latest_version, release_date = get_latest_vscode_release()

    print(f"Current manifest version: {current_version}")
    print(f"Latest upstream version:  {latest_version} ({release_date})")

    if current_version == latest_version and not args.force:
        if not VERSION_PATH.exists() or VERSION_PATH.read_text(encoding="utf-8").strip() != latest_version:
            if not args.check_only:
                VERSION_PATH.write_text(f"{latest_version}\n", encoding="utf-8")
        print("Already up to date.")
        write_github_output(False, latest_version, current_version)
        return 0

    if args.check_only:
        print(f"Update available: {current_version} -> {latest_version}")
        write_github_output(True, latest_version, current_version)
        return 0

    print(f"Fetching deb metadata for VSCode {latest_version}...")
    x64_meta = get_deb_metadata(latest_version, "x64")
    arm64_meta = get_deb_metadata(latest_version, "arm64")
    print(f"  x86_64:  sha256={x64_meta[1]} size={x64_meta[2]}")
    print(f"  aarch64: sha256={arm64_meta[1]} size={arm64_meta[2]}")

    new_manifest = update_manifest(manifest_text, x64_meta, arm64_meta)
    MANIFEST_PATH.write_text(new_manifest, encoding="utf-8")

    metainfo_text = METAINFO_PATH.read_text(encoding="utf-8")
    new_metainfo = update_metainfo(metainfo_text, latest_version, release_date)
    METAINFO_PATH.write_text(new_metainfo, encoding="utf-8")

    VERSION_PATH.write_text(f"{latest_version}\n", encoding="utf-8")
    print(f"Updated com.visualstudio.code manifest to {latest_version}.")
    write_github_output(True, latest_version, current_version)
    return 0


if __name__ == "__main__":
    sys.exit(main())
