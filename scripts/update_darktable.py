#!/usr/bin/env python3
"""Track the latest darktable release, upstream Flathub modules/shared-modules, and onnxruntime."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import urllib.parse
import urllib.request


REPO_ROOT = Path(__file__).resolve().parent.parent
APP_DIR = REPO_ROOT / "apps" / "org.darktable.Darktable"
MANIFEST_PATH = APP_DIR / "org.darktable.Darktable.json"
EXIFTOOL_PATH = APP_DIR / "exiftool-sources.json"
LENSFUN_SCRIPT_PATH = APP_DIR / "lensfun_convert_db.py"
METAINFO_PATH = APP_DIR / "org.darktable.Darktable.metainfo.xml"
VERSION_PATH = APP_DIR / "VERSION"

ONNXRUNTIME_DEP_NAMES = (
    "abseil_cpp",
    "date",
    "eigen",
    "flatbuffers",
    "json",
    "microsoft_gsl",
    "mp11",
    "onnx",
    "protobuf",
    "pytorch_cpuinfo",
    "re2",
    "safeint",
)


def github_headers(accept: str = "application/vnd.github+json") -> dict[str, str]:
    headers = {
        "Accept": accept,
        "User-Agent": "luzechao-flatpak-updater",
    }
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def fetch_json(url: str) -> dict | list:
    req = urllib.request.Request(url, headers=github_headers())
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def fetch_text(url: str) -> str:
    req = urllib.request.Request(
        url, headers={"User-Agent": "luzechao-flatpak-updater"}
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        return resp.read().decode("utf-8")


def compute_url_sha256(url: str) -> str:
    req = urllib.request.Request(
        url, headers={"User-Agent": "luzechao-flatpak-updater"}
    )
    h = hashlib.sha256()
    with urllib.request.urlopen(req, timeout=300) as resp:
        while True:
            chunk = resp.read(1024 * 1024)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest().lower()


def get_latest_darktable_release() -> tuple[str, str, str, str | None]:
    data = fetch_json("https://api.github.com/repos/darktable-org/darktable/releases/latest")
    assert isinstance(data, dict)

    tag_name = data["tag_name"]
    version = re.sub(r"^(release-|v)", "", tag_name)
    published_at = data.get("published_at", "")[:10]

    expected_asset_name = f"darktable-{version}.tar.xz"
    tarball_url = (
        f"https://github.com/darktable-org/darktable/releases/download/"
        f"{tag_name}/{expected_asset_name}"
    )
    sha256 = None

    for asset in data.get("assets", []):
        if asset.get("name") == expected_asset_name:
            tarball_url = asset.get("browser_download_url", tarball_url)
            digest = asset.get("digest", "")
            if isinstance(digest, str) and digest.startswith("sha256:"):
                sha256 = digest.split(":", 1)[1].strip().lower()
            break

    return version, published_at, tarball_url, sha256


def get_latest_onnxruntime_tag_and_commit() -> tuple[str, str]:
    data = fetch_json("https://api.github.com/repos/microsoft/onnxruntime/releases/latest")
    assert isinstance(data, dict)
    tag = data["tag_name"]

    ref_data = fetch_json(
        f"https://api.github.com/repos/microsoft/onnxruntime/git/ref/tags/{tag}"
    )
    assert isinstance(ref_data, dict)
    obj = ref_data["object"]
    commit_sha = obj["sha"]
    if obj.get("type") == "tag":
        tag_obj = fetch_json(obj["url"])
        assert isinstance(tag_obj, dict)
        commit_sha = tag_obj["object"]["sha"]
    return tag, commit_sha


def build_onnxruntime_module(
    existing_onnx_mod: dict | None, update_onnx: bool = False
) -> dict:
    if existing_onnx_mod and not update_onnx:
        return existing_onnx_mod

    existing_sources = (existing_onnx_mod or {}).get("sources", [])
    existing_git = next(
        (s for s in existing_sources if isinstance(s, dict) and s.get("type") == "git"),
        {},
    )
    current_tag = existing_git.get("tag")
    current_commit = existing_git.get("commit")

    existing_sha256_by_url = {
        s["url"]: s["sha256"]
        for s in existing_sources
        if isinstance(s, dict) and s.get("type") == "file" and "url" in s and "sha256" in s
    }

    try:
        latest_tag, latest_commit = get_latest_onnxruntime_tag_and_commit()
    except Exception as exc:
        print(f"Warning: could not query latest onnxruntime release ({exc}), keeping {current_tag}")
        if existing_onnx_mod:
            return existing_onnx_mod
        raise

    print(f"Updating onnxruntime module: {current_tag} -> {latest_tag} ({latest_commit[:10]})")
    deps_txt = fetch_text(
        f"https://raw.githubusercontent.com/microsoft/onnxruntime/{latest_tag}/cmake/deps.txt"
    )
    dep_urls: dict[str, str] = {}
    for line in deps_txt.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split(";")
        if len(parts) >= 2:
            dep_urls[parts[0]] = parts[1]

    sources: list[dict[str, str]] = [
        {
            "type": "git",
            "url": "https://github.com/microsoft/onnxruntime.git",
            "tag": latest_tag,
            "commit": latest_commit,
        }
    ]

    for dep_name in ONNXRUNTIME_DEP_NAMES:
        dep_url = dep_urls.get(dep_name)
        if not dep_url:
            continue
        parsed = urllib.parse.urlparse(dep_url)
        rel_path = parsed.path.lstrip("/")
        dest_dir = f"external-deps/{parsed.netloc}/{os.path.dirname(rel_path)}"
        dest_filename = os.path.basename(rel_path)
        sha256 = existing_sha256_by_url.get(dep_url)
        if not sha256 or update_onnx:
            print(f"  Computing SHA256 for onnxruntime dep {dep_name} ({dest_filename})...")
            sha256 = compute_url_sha256(dep_url)
        sources.append(
            {
                "type": "file",
                "url": dep_url,
                "sha256": sha256,
                "dest": dest_dir,
                "dest-filename": dest_filename,
            }
        )

    return {
        "name": "onnxruntime",
        "buildsystem": "cmake-ninja",
        "builddir": True,
        "subdir": "cmake",
        "config-opts": [
            "--compile-no-warning-as-error",
            "-DCMAKE_BUILD_TYPE=Release",
            "-Donnxruntime_CMAKE_DEPS_MIRROR_DIR=../../external-deps",
            "-Donnxruntime_BUILD_SHARED_LIB=ON",
            "-Donnxruntime_BUILD_UNIT_TESTS=OFF",
        ],
        "sources": sources,
    }


def sync_shared_modules(shared_mod_paths: list[str], check_only: bool) -> bool:
    if not shared_mod_paths:
        return False

    try:
        sub_info = fetch_json(
            "https://api.github.com/repos/flathub/org.darktable.Darktable/contents/shared-modules?ref=master"
        )
        assert isinstance(sub_info, dict)
        submodule_sha = sub_info.get("sha", "master")
    except Exception:
        submodule_sha = "master"

    changed = False
    for rel_json_path in shared_mod_paths:
        # e.g. "shared-modules/lua5.4/lua-5.4.json"
        sub_rel = rel_json_path.removeprefix("shared-modules/").lstrip("/")
        sub_dir = os.path.dirname(sub_rel)
        try:
            dir_entries = fetch_json(
                f"https://api.github.com/repos/flathub/shared-modules/contents/{sub_dir}?ref={submodule_sha}"
            )
            if not isinstance(dir_entries, list):
                continue
            for entry in dir_entries:
                if not isinstance(entry, dict) or entry.get("type") != "file":
                    continue
                dl_url = entry.get("download_url")
                fname = entry.get("name")
                if not dl_url or not fname:
                    continue
                content = fetch_text(dl_url)
                if fname == "lua-5.4.json":
                    mod_obj = json.loads(content)
                    for src in mod_obj.get("sources", []):
                        if isinstance(src, dict) and src.get("url") == "https://www.lua.org/ftp/lua-5.4.6.tar.gz":
                            src["mirror-urls"] = [
                                "https://src.fedoraproject.org/repo/pkgs/lua/lua-5.4.6.tar.gz/sha512/d90c6903355ee1309cb0d92a8a024522ff049091a117ea21efb585b5de35776191cd67d17a65b18c2f9d374795b7c944f047576f0e3fe818d094b26f0e4845c5/lua-5.4.6.tar.gz"
                            ]
                    content = json.dumps(mod_obj, indent=4) + "\n"
                elif fname == "intltool-0.51.json":
                    mod_obj = json.loads(content)
                    for src in mod_obj.get("sources", []):
                        if isinstance(src, dict) and src.get("url") == "https://launchpad.net/intltool/trunk/0.51.0/+download/intltool-0.51.0.tar.gz":
                            src["mirror-urls"] = [
                                "https://deb.debian.org/debian/pool/main/i/intltool/intltool_0.51.0.orig.tar.gz"
                            ]
                    content = json.dumps(mod_obj, indent=2) + "\n"
                local_file = APP_DIR / "shared-modules" / sub_dir / fname
                existing = (
                    local_file.read_text(encoding="utf-8")
                    if local_file.exists()
                    else None
                )
                if existing != content:
                    changed = True
                    print(f"Upstream shared-module file updated: shared-modules/{sub_dir}/{fname}")
                    if not check_only:
                        local_file.parent.mkdir(parents=True, exist_ok=True)
                        local_file.write_text(content, encoding="utf-8")
        except Exception as exc:
            print(f"Warning: failed to check shared-module {rel_json_path}: {exc}")

    return changed


def get_current_manifest_version(manifest_text: str) -> str | None:
    m = re.search(
        r"https://github\.com/darktable-org/darktable/releases/download/[^/]+/darktable-([0-9.]+)\.tar\.xz",
        manifest_text,
    )
    return m.group(1) if m else None


def find_module(data: dict, name: str) -> dict | None:
    for mod in data.get("modules", []):
        if isinstance(mod, dict) and mod.get("name") == name:
            return mod
    return None


def build_updated_manifest(
    local_manifest_text: str,
    tarball_url: str,
    tarball_sha256: str,
    update_onnx: bool = False,
) -> tuple[str, list[str]]:
    local_data = json.loads(local_manifest_text)
    existing_onnx_mod = find_module(local_data, "onnxruntime")

    try:
        upstream_text = fetch_text(
            "https://raw.githubusercontent.com/flathub/org.darktable.Darktable/master/org.darktable.Darktable.json"
        )
        base_data = json.loads(upstream_text)
    except Exception as exc:
        print(f"Warning: could not fetch upstream flathub manifest ({exc}), using local manifest as base")
        base_data = local_data

    # Prefer upstream's onnxruntime module if Flathub has merged PR #252
    upstream_onnx_mod = find_module(base_data, "onnxruntime")
    base_onnx_mod = upstream_onnx_mod or existing_onnx_mod

    # Ensure build-options.no-debuginfo is set right after copy-icon
    ordered_top: dict = {}
    inserted_build_opts = False
    for k, v in base_data.items():
        if k == "no-debuginfo":
            continue
        ordered_top[k] = v
        if k == "copy-icon":
            bopts = dict(base_data.get("build-options", {}))
            bopts["no-debuginfo"] = True
            ordered_top["build-options"] = bopts
            inserted_build_opts = True
    if not inserted_build_opts:
        bopts = dict(ordered_top.get("build-options", {}))
        bopts["no-debuginfo"] = True
        ordered_top["build-options"] = bopts

    onnx_mod = build_onnxruntime_module(base_onnx_mod, update_onnx=update_onnx)

    new_modules = []
    shared_mod_paths: list[str] = []
    for mod in ordered_top.get("modules", []):
        if isinstance(mod, str) and mod.startswith("shared-modules/"):
            shared_mod_paths.append(mod)
        if isinstance(mod, dict) and mod.get("name") == "onnxruntime":
            continue
        if isinstance(mod, dict) and mod.get("name") == "gmic":
            for src in mod.get("sources", []):
                if isinstance(src, dict) and src.get("type") == "archive":
                    m_gmic = re.search(r"gmic_([0-9.]+)\.tar\.gz$", src.get("url", ""))
                    if m_gmic:
                        gmic_ver = m_gmic.group(1)
                        gh_url = f"https://github.com/GreycLab/gmic/releases/download/v.{gmic_ver}/gmic_{gmic_ver}.tar.gz"
                        orig_url = f"https://gmic.eu/files/source/gmic_{gmic_ver}.tar.gz"
                        reordered_src: dict = {
                            "type": "archive",
                            "url": gh_url,
                            "mirror-urls": [orig_url],
                            "sha256": src["sha256"],
                        }
                        if "x-checker-data" in src and isinstance(src["x-checker-data"], dict):
                            checker = dict(src["x-checker-data"])
                            checker["url-template"] = (
                                "https://github.com/GreycLab/gmic/releases/download/v.$version/gmic_$version.tar.gz"
                            )
                            reordered_src["x-checker-data"] = checker
                        src.clear()
                        src.update(reordered_src)
        if isinstance(mod, dict) and mod.get("name") == "potrace":
            for src in mod.get("sources", []):
                if isinstance(src, dict) and src.get("type") == "archive":
                    m_pot = re.search(r"potrace-([0-9.]+)\.tar\.gz$", src.get("url", ""))
                    if m_pot:
                        pot_ver = m_pot.group(1)
                        reordered_src = {
                            "type": "archive",
                            "url": f"https://potrace.sourceforge.net/download/{pot_ver}/potrace-{pot_ver}.tar.gz",
                            "mirror-urls": [
                                f"https://deb.debian.org/debian/pool/main/p/potrace/potrace_{pot_ver}.orig.tar.gz",
                                f"https://downloads.sourceforge.net/project/potrace/{pot_ver}/potrace-{pot_ver}.tar.gz",
                            ],
                            "sha256": src["sha256"],
                        }
                        src.clear()
                        src.update(reordered_src)
        if isinstance(mod, dict) and mod.get("name") == "darktable":
            new_modules.append(onnx_mod)
            config_opts = mod.setdefault("config-opts", [])
            if "-DUSE_AI=ON" not in config_opts:
                config_opts.append("-DUSE_AI=ON")
            if "-DONNXRUNTIME_OFFLINE=ON" not in config_opts:
                config_opts.append("-DONNXRUNTIME_OFFLINE=ON")
            for src in mod.get("sources", []):
                if isinstance(src, dict) and src.get("type") == "archive":
                    src["url"] = tarball_url
                    src["sha256"] = tarball_sha256
                    break
        if isinstance(mod, dict) and mod.get("name") == "exiv2":
            mod.setdefault("build-options", {})[
                "ldflags"
            ] = "-Wl,-rpath-link,/app/lib64"
        new_modules.append(mod)

    ordered_top["modules"] = new_modules
    return json.dumps(ordered_top, indent=4) + "\n", shared_mod_paths


def sync_auxiliary_flathub_files(check_only: bool) -> bool:
    changed = False
    aux_files = [
        (
            "https://raw.githubusercontent.com/flathub/org.darktable.Darktable/master/exiftool-sources.json",
            EXIFTOOL_PATH,
        ),
        (
            "https://raw.githubusercontent.com/flathub/org.darktable.Darktable/master/lensfun_convert_db.py",
            LENSFUN_SCRIPT_PATH,
        ),
    ]
    for url, path in aux_files:
        try:
            remote_text = fetch_text(url)
            local_text = path.read_text(encoding="utf-8") if path.exists() else None
            if local_text != remote_text:
                changed = True
                print(f"Upstream auxiliary file updated: {path.name}")
                if not check_only:
                    path.write_text(remote_text, encoding="utf-8")
        except Exception as exc:
            print(f"Warning: could not check {path.name}: {exc}")
    return changed


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


def write_github_output(
    updated: bool, version: str, current_version: str | None
) -> None:
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
        help="Refresh hashes even if the version matches.",
    )
    parser.add_argument(
        "--update-onnxruntime",
        action="store_true",
        help="Also upgrade onnxruntime and its cmake/deps.txt dependencies to the latest upstream release.",
    )
    args = parser.parse_args()

    manifest_text = MANIFEST_PATH.read_text(encoding="utf-8")
    current_version = get_current_manifest_version(manifest_text)
    latest_version, release_date, tarball_url, api_sha256 = (
        get_latest_darktable_release()
    )

    print(f"Current darktable manifest version: {current_version}")
    print(f"Latest upstream darktable version:  {latest_version} ({release_date})")

    # Reuse existing sha256 if version matches and api_sha256 is unavailable
    existing_darktable_mod = find_module(json.loads(manifest_text), "darktable") or {}
    existing_sha256 = next(
        (
            s.get("sha256")
            for s in existing_darktable_mod.get("sources", [])
            if isinstance(s, dict) and s.get("url") == tarball_url
        ),
        None,
    )
    sha256 = api_sha256 or existing_sha256
    if not sha256 or args.force:
        print(f"Downloading {tarball_url} to compute SHA256...")
        sha256 = compute_url_sha256(tarball_url)

    new_manifest, shared_mod_paths = build_updated_manifest(
        manifest_text, tarball_url, sha256, update_onnx=args.update_onnxruntime
    )
    manifest_changed = new_manifest != manifest_text
    aux_changed = sync_auxiliary_flathub_files(check_only=args.check_only)
    shared_changed = sync_shared_modules(shared_mod_paths, check_only=args.check_only)

    any_changed = (
        (current_version != latest_version)
        or manifest_changed
        or aux_changed
        or shared_changed
        or args.force
    )

    if not any_changed:
        if (
            not VERSION_PATH.exists()
            or VERSION_PATH.read_text(encoding="utf-8").strip() != latest_version
        ):
            if not args.check_only:
                VERSION_PATH.write_text(f"{latest_version}\n", encoding="utf-8")
        print("Already up to date (darktable release, Flathub modules, shared-modules, and onnxruntime).")
        write_github_output(False, latest_version, current_version)
        return 0

    if args.check_only:
        print(
            f"Update available: version {current_version} -> {latest_version} "
            f"(manifest_changed={manifest_changed}, aux_changed={aux_changed}, shared_changed={shared_changed})"
        )
        write_github_output(True, latest_version, current_version)
        return 0

    MANIFEST_PATH.write_text(new_manifest, encoding="utf-8")

    if METAINFO_PATH.exists():
        metainfo_text = METAINFO_PATH.read_text(encoding="utf-8")
        new_metainfo = update_metainfo(metainfo_text, latest_version, release_date)
        METAINFO_PATH.write_text(new_metainfo, encoding="utf-8")

    VERSION_PATH.write_text(f"{latest_version}\n", encoding="utf-8")
    print(f"Updated org.darktable.Darktable manifest and modules (version {latest_version}).")
    write_github_output(True, latest_version, current_version)
    return 0


if __name__ == "__main__":
    sys.exit(main())
