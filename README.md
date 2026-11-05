# Zechao Flatpak Channel

Personal Flatpak channel hosted on GitHub Pages (`https://luzechao.github.io/flatpak/`), built and updated automatically via GitHub Actions.

## Quick Start

### 1. Add the Flatpak Remote

Ensure Flathub is configured (used for base runtimes such as `org.freedesktop.Platform` and `org.electronjs.Electron2.BaseApp`), then add this channel:

```bash
flatpak remote-add --if-not-exists flathub https://dl.flathub.org/repo/flathub.flatpakrepo
flatpak remote-add --if-not-exists luzechao https://luzechao.github.io/flatpak/flatpak.flatpakrepo
```

### 2. Install Visual Studio Code

```bash
flatpak install luzechao com.visualstudio.code
```

 Or install directly via `.flatpakref`:

```bash
flatpak install https://luzechao.github.io/flatpak/com.visualstudio.code.flatpakref
```

### 3. Update Installed Packages

```bash
flatpak update
```

---

## Available Packages

| Application | App ID | Upstream Tracked | Manifest |
| :--- | :--- | :--- | :--- |
| **Visual Studio Code** | `com.visualstudio.code` | [`microsoft/vscode`](https://github.com/microsoft/vscode/releases) | [`apps/com.visualstudio.code/com.visualstudio.code.yaml`](apps/com.visualstudio.code/com.visualstudio.code.yaml) |

---

## How It Works

1. **Automated Upstream Tracking**:
   - The [Flatpak Channel CI](.github/workflows/flatpak-channel.yml) workflow runs every 6 hours (and on push / manual dispatch).
   - [`scripts/update_vscode.py`](scripts/update_vscode.py) queries `https://api.github.com/repos/microsoft/vscode/releases/latest` and compares it with [`apps/com.visualstudio.code/VERSION`](apps/com.visualstudio.code/VERSION).
   - When a new VSCode release is published, the script fetches the new `.deb` SHA256 checksums and file sizes from `update.code.visualstudio.com`, updates the Flatpak manifest and AppStream metainfo, and commits the update to `main`.
2. **Flatpak Build & OSTree Publishing**:
   - [`scripts/build_and_publish.sh`](scripts/build_and_publish.sh) builds changed applications using `flatpak-builder`, signs the commits and summary with the repository GPG key, exports them into the persistent OSTree repository on the `gh-pages` branch, and publishes static deltas, `.flatpakref` files, and a GitHub Release bundle.

---

## Adding More Flatpak Applications to This Channel

This repository is structured to host multiple Flatpak applications in a single shared OSTree channel:

1. Create a new directory under `apps/<app-id>/`:
   ```text
   apps/<app-id>/
   ├── <app-id>.yaml          # (or .yml / .json) Flatpak manifest
   ├── <app-id>.metainfo.xml  # AppStream metadata
   ├── VERSION                # Current package version string
   └── update.py              # (Optional) Script to auto-update manifest from upstream
   ```
2. Push to `main` (or trigger the workflow via `workflow_dispatch`).
3. [`scripts/detect_builds.py`](scripts/detect_builds.py) will automatically detect that `<app-id>@<VERSION>` is not yet published in `gh-pages/apps.json`, build the package, and export it into the existing OSTree repository on `gh-pages` alongside all existing packages.
