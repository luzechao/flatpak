#!/usr/bin/env python3
"""Generate channel metadata (.flatpakrepo, .flatpakref, apps.json, index.html) for GitHub Pages."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import html
import json
from pathlib import Path
import shutil
import xml.etree.ElementTree as ET


REPO_ROOT = Path(__file__).resolve().parent.parent
CHANNEL_DIR = REPO_ROOT / "channel"
APPS_DIR = REPO_ROOT / "apps"
CHANNEL_URL = "https://luzechao.github.io/flatpak/"
GITHUB_REPO_URL = "https://github.com/luzechao/flatpak"


def parse_app_metadata(app_dir: Path) -> dict[str, str]:
    app_id = app_dir.name
    name = app_id
    summary = ""
    homepage = ""
    version = "latest"

    version_file = app_dir / "VERSION"
    if version_file.exists():
        version = version_file.read_text(encoding="utf-8").strip()

    metainfo_candidates = list(app_dir.glob(f"{app_id}.metainfo.xml")) + list(
        app_dir.glob(f"{app_id}.appdata.xml")
    )
    if metainfo_candidates:
        try:
            tree = ET.parse(metainfo_candidates[0])
            root = tree.getroot()
            name_el = root.find("name")
            if name_el is not None and name_el.text:
                name = name_el.text.strip()
            sum_el = root.find("summary")
            if sum_el is not None and sum_el.text:
                summary = sum_el.text.strip()
            for url_el in root.findall("url"):
                if url_el.get("type") == "homepage" and url_el.text:
                    homepage = url_el.text.strip()
                    break
            if version == "latest":
                rel_el = root.find("./releases/release")
                if rel_el is not None and rel_el.get("version"):
                    version = rel_el.get("version", "latest")
        except Exception as exc:
            print(f"Warning: failed to parse metainfo for {app_id}: {exc}")

    return {
        "app_id": app_id,
        "name": name,
        "summary": summary,
        "homepage": homepage,
        "version": version,
        "branch": "stable",
        "updated_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
    }


def generate_flatpakref(app: dict[str, str], gpg_b64: str) -> str:
    lines = [
        "[Flatpak Ref]",
        f"Name={app['app_id']}",
        "Branch=stable",
        f"Title={app['name']} from Zechao Flatpak Channel",
        "IsRuntime=false",
        f"Url={CHANNEL_URL}",
        "SuggestRemoteName=luzechao",
        "RuntimeRepo=https://dl.flathub.org/repo/flathub.flatpakrepo",
    ]
    if gpg_b64:
        lines.append(f"GPGKey={gpg_b64}")
    return "\n".join(lines) + "\n"


def generate_index_html(apps: dict[str, dict[str, str]]) -> str:
    app_cards = []
    for app_id, info in sorted(apps.items()):
        esc_id = html.escape(app_id)
        esc_name = html.escape(info.get("name", app_id))
        esc_summary = html.escape(info.get("summary", ""))
        esc_version = html.escape(info.get("version", ""))
        esc_updated = html.escape(info.get("updated_at", ""))
        homepage = info.get("homepage", "")
        homepage_link = (
            f'<a href="{html.escape(homepage)}" target="_blank" rel="noopener">Upstream</a> · '
            if homepage
            else ""
        )
        app_cards.append(
            f"""
      <div class="card">
        <div class="card-header">
          <div>
            <h3>{esc_name}</h3>
            <code class="app-id">{esc_id}</code>
          </div>
          <span class="badge">v{esc_version}</span>
        </div>
        <p class="summary">{esc_summary}</p>
        <pre><code>flatpak install luzechao {esc_id}</code></pre>
        <div class="meta">
          <span>Updated: {esc_updated}</span>
          <span>{homepage_link}<a href="{esc_id}.flatpakref">{esc_id}.flatpakref</a></span>
        </div>
      </div>"""
        )

    cards_html = "\n".join(app_cards) if app_cards else "<p>No packages published yet.</p>"

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Zechao Flatpak Channel</title>
  <style>
    :root {{
      color-scheme: light dark;
      --bg: #0f172a;
      --surface: #1e293b;
      --border: #334155;
      --text: #f8fafc;
      --muted: #94a3b8;
      --accent: #38bdf8;
      --code-bg: #0b1120;
    }}
    @media (prefers-color-scheme: light) {{
      :root {{
        --bg: #f8fafc;
        --surface: #ffffff;
        --border: #e2e8f0;
        --text: #0f172a;
        --muted: #475569;
        --accent: #0284c7;
        --code-bg: #f1f5f9;
      }}
    }}
    * {{ box-sizing: border-box; }}
    body {{
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      background: var(--bg);
      color: var(--text);
      margin: 0;
      padding: 2.5rem 1.25rem;
      line-height: 1.6;
    }}
    .container {{
      max-width: 860px;
      margin: 0 auto;
    }}
    header {{
      margin-bottom: 2rem;
      border-bottom: 1px solid var(--border);
      padding-bottom: 1.5rem;
    }}
    h1 {{ margin: 0 0 0.5rem 0; font-size: 2rem; }}
    h2 {{ margin-top: 2rem; font-size: 1.35rem; }}
    p {{ margin: 0.5rem 0; color: var(--muted); }}
    a {{ color: var(--accent); text-decoration: none; }}
    a:hover {{ text-decoration: underline; }}
    pre {{
      background: var(--code-bg);
      border: 1px solid var(--border);
      border-radius: 8px;
      padding: 0.9rem 1rem;
      overflow-x: auto;
      margin: 0.75rem 0;
    }}
    code {{
      font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
      font-size: 0.9rem;
    }}
    .card {{
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: 10px;
      padding: 1.25rem;
      margin-bottom: 1rem;
    }}
    .card-header {{
      display: flex;
      justify-content: space-between;
      align-items: flex-start;
      gap: 1rem;
    }}
    .card-header h3 {{ margin: 0; font-size: 1.2rem; }}
    .app-id {{ color: var(--muted); font-size: 0.85rem; }}
    .badge {{
      background: var(--accent);
      color: #fff;
      font-weight: 600;
      font-size: 0.8rem;
      padding: 0.2rem 0.65rem;
      border-radius: 999px;
      white-space: nowrap;
    }}
    .summary {{ margin: 0.6rem 0; color: var(--text); }}
    .meta {{
      display: flex;
      justify-content: space-between;
      flex-wrap: wrap;
      gap: 0.5rem;
      font-size: 0.82rem;
      color: var(--muted);
      margin-top: 0.5rem;
    }}
    footer {{
      margin-top: 3rem;
      padding-top: 1rem;
      border-top: 1px solid var(--border);
      font-size: 0.85rem;
      color: var(--muted);
      display: flex;
      justify-content: space-between;
      flex-wrap: wrap;
    }}
  </style>
</head>
<body>
  <div class="container">
    <header>
      <h1>Zechao Flatpak Channel</h1>
      <p>Automated Flatpak repository hosted on GitHub Pages (<a href="{GITHUB_REPO_URL}">luzechao/flatpak</a>).</p>
    </header>

    <section>
      <h2>1. Add the Flatpak Remote</h2>
      <p>Ensure Flathub is enabled (for base runtimes), then add this channel:</p>
      <pre><code>flatpak remote-add --if-not-exists flathub https://dl.flathub.org/repo/flathub.flatpakrepo
flatpak remote-add --if-not-exists luzechao {CHANNEL_URL}flatpak.flatpakrepo</code></pre>
    </section>

    <section>
      <h2>2. Available Applications</h2>
      {cards_html}
    </section>

    <section>
      <h2>3. Updating Packages</h2>
      <pre><code>flatpak update</code></pre>
    </section>

    <footer>
      <span>Repository files: <a href="flatpak.flatpakrepo">flatpak.flatpakrepo</a> · <a href="gpg.pub">gpg.pub</a> · <a href="apps.json">apps.json</a></span>
      <span>Powered by GitHub Actions &amp; OSTree</span>
    </footer>
  </div>
</body>
</html>
"""


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        required=True,
        type=Path,
        help="Path to the target GitHub Pages / OSTree repository directory.",
    )
    parser.add_argument(
        "--app-id",
        help="Specific app ID being updated (if omitted, scans all apps in apps/).",
    )
    args = parser.parse_args()

    out_dir: Path = args.output_dir.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    (out_dir / ".nojekyll").write_text("", encoding="utf-8")

    for fname in ("flatpak.flatpakrepo", "luzechao.flatpakrepo", "gpg.pub"):
        src = CHANNEL_DIR / fname
        if src.exists():
            shutil.copyfile(src, out_dir / fname)

    gpg_b64 = ""
    gpg_b64_file = CHANNEL_DIR / "gpg.bin.b64"
    if gpg_b64_file.exists():
        gpg_b64 = gpg_b64_file.read_text(encoding="utf-8").strip()

    apps_json_path = out_dir / "apps.json"
    apps_catalog: dict[str, dict[str, str]] = {}
    if apps_json_path.exists():
        try:
            apps_catalog = json.loads(apps_json_path.read_text(encoding="utf-8"))
        except Exception:
            apps_catalog = {}

    if args.app_id:
        target_dirs = [APPS_DIR / args.app_id]
    else:
        target_dirs = [p for p in sorted(APPS_DIR.iterdir()) if p.is_dir()]

    for app_dir in target_dirs:
        if not app_dir.is_dir():
            continue
        meta = parse_app_metadata(app_dir)
        apps_catalog[meta["app_id"]] = meta
        flatpakref_content = generate_flatpakref(meta, gpg_b64)
        (out_dir / f"{meta['app_id']}.flatpakref").write_text(
            flatpakref_content, encoding="utf-8"
        )

    apps_json_path.write_text(
        json.dumps(apps_catalog, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (out_dir / "index.html").write_text(
        generate_index_html(apps_catalog),
        encoding="utf-8",
    )
    print(f"Generated channel site in {out_dir} for {len(apps_catalog)} app(s).")


if __name__ == "__main__":
    main()
