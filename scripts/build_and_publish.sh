#!/usr/bin/env bash
set -euo pipefail

if [ $# -lt 2 ]; then
  echo "Usage: $0 <app-id> <ostree-repo-dir> [bundle-output-path]" >&2
  exit 1
fi

APP_ID="$1"
REPO_DIR="$(realpath -m "$2")"
BUNDLE_OUT="${3:-}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
APP_DIR="${ROOT_DIR}/apps/${APP_ID}"

if [ ! -d "${APP_DIR}" ]; then
  echo "Error: App directory not found: ${APP_DIR}" >&2
  exit 1
fi

if [ -f "${APP_DIR}/${APP_ID}.yaml" ]; then
  MANIFEST="${APP_ID}.yaml"
elif [ -f "${APP_DIR}/${APP_ID}.yml" ]; then
  MANIFEST="${APP_ID}.yml"
elif [ -f "${APP_DIR}/${APP_ID}.json" ]; then
  MANIFEST="${APP_ID}.json"
else
  echo "Error: No Flatpak manifest found in ${APP_DIR}" >&2
  exit 1
fi

mkdir -p "${REPO_DIR}"
if [ ! -f "${REPO_DIR}/config" ]; then
  echo "Initializing new OSTree repository at ${REPO_DIR}..."
  ostree init --repo="${REPO_DIR}" --mode=archive-z2
fi
mkdir -p "${REPO_DIR}"/{extensions,tmp/cache,objects,refs/remotes,refs/mirrors,refs/heads,state}

GPG_ARGS=()
if [ -n "${FLATPAK_GPG_PRIVATE_KEY:-}" ]; then
  GNUPGHOME="$(mktemp -d)"
  chmod 700 "${GNUPGHOME}"
  export GNUPGHOME
  trap 'rm -rf "${GNUPGHOME}"' EXIT
  echo "${FLATPAK_GPG_PRIVATE_KEY}" | gpg --batch --import
  KEY_ID="${FLATPAK_GPG_KEY_ID:-}"
  if [ -z "${KEY_ID}" ]; then
    KEY_ID="$(gpg --list-secret-keys --with-colons | awk -F: '/^fpr:/ {print $10; exit}')"
  fi
  echo "Using GPG key ${KEY_ID} for signing."
  GPG_ARGS=(--gpg-sign="${KEY_ID}" --gpg-homedir="${GNUPGHOME}")
fi

flatpak remote-add --user --if-not-exists flathub https://dl.flathub.org/repo/flathub.flatpakrepo

BUILD_DIR="${RUNNER_TEMP:-/tmp}/flatpak-build-${APP_ID}"
STATE_DIR="${FLATPAK_BUILDER_STATE_DIR:-${ROOT_DIR}/.flatpak-builder}"

pushd "${APP_DIR}" >/dev/null
echo "Building ${APP_ID} from ${MANIFEST}..."
flatpak-builder \
  --force-clean \
  --disable-rofiles-fuse \
  --user \
  --install-deps-from=flathub \
  --default-branch=stable \
  --state-dir="${STATE_DIR}" \
  --repo="${REPO_DIR}" \
  "${GPG_ARGS[@]}" \
  "${BUILD_DIR}" \
  "${MANIFEST}"
popd >/dev/null

echo "Updating OSTree repository metadata and static deltas..."
flatpak build-update-repo \
  "${REPO_DIR}" \
  --title="Zechao Flatpak Channel" \
  --generate-static-deltas \
  --prune \
  --prune-depth=2 \
  "${GPG_ARGS[@]}"

if [ -n "${BUNDLE_OUT}" ]; then
  BUNDLE_PATH="$(realpath -m "${BUNDLE_OUT}")"
  mkdir -p "$(dirname "${BUNDLE_PATH}")"
  echo "Creating single-file Flatpak bundle at ${BUNDLE_PATH}..."
  flatpak build-bundle \
    "${REPO_DIR}" \
    "${BUNDLE_PATH}" \
    "${APP_ID}" \
    stable \
    --runtime-repo=https://dl.flathub.org/repo/flathub.flatpakrepo
fi

echo "Generating GitHub Pages channel files..."
python3 "${SCRIPT_DIR}/generate_channel_site.py" \
  --output-dir "${REPO_DIR}" \
  --app-id "${APP_ID}"

rm -rf "${REPO_DIR}/tmp/cache" "${REPO_DIR}/.lock" "${BUILD_DIR}"
mkdir -p "${REPO_DIR}/tmp"
echo "Successfully built and published ${APP_ID} into ${REPO_DIR}."
