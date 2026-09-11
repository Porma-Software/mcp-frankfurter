#!/usr/bin/env bash
# Copyright (c) 2026 Nahúm Cueto López (Porma Software)
# SPDX-License-Identifier: MIT
#
# Local reproduction of the gitleaks-history job in .github/workflows/secrets.yml (secret
# guardrail layer 3: the FULL git history, upstream rule set). `make` is not available on the
# Windows dev machine, so this is the direct command to run there.
#
# Git Bash on Windows ships MSYS, whose runtime rewrites any argument that looks like a POSIX
# path before it reaches a non-MSYS executable such as docker.exe -- including a container-side
# path like "/repo" that was never meant to resolve on the host. Left alone, "/repo" becomes the
# MSYS install root (e.g. "C:/Program Files/Git/repo"), so gitleaks is asked to scan a path that
# only exists on the MSYS side and fails with "no such file or directory". MSYS_NO_PATHCONV=1
# turns that rewriting off for this one command; it does nothing outside Git Bash, so the script
# is identical to run on Linux, macOS or inside CI.
#
# Usage: bash scripts/scan-secrets-local.sh   (run from the repo root)
#
# A worktree checkout also keeps its real git metadata outside the working directory (its
# ".git" is a one-line pointer file, see `git worktree list`), so mounting the working directory
# alone leaves the container unable to resolve the repository at all -- a second, unrelated
# failure behind the same "no such file or directory" symptom. Cloning into a throwaway local
# directory first sidesteps that: same commits, same history, an ordinary self-contained ".git"
# with nothing for the container to resolve outside the mount.
set -euo pipefail

# Pinned by tag; digest at the time of pinning:
# sha256:c00b6bd0aeb3071cbcb79009cb16a60dd9e0a7c60e2be9ab65d25e6bc8abbb7f
image="zricethezav/gitleaks:v8.30.1"
docker pull -q "$image"

scan_dir="$PWD/.gitleaks-scan"
rm -rf "$scan_dir"
trap 'rm -rf "$scan_dir"' EXIT
git clone --quiet --local --no-hardlinks . "$scan_dir"

export MSYS_NO_PATHCONV=1

# GIT_CONFIG_*: the container runs as a different uid than the checkout owner; git refuses to
# read a repository it does not own without this.
rc=0
docker run --rm -v "$scan_dir:/repo" \
  -e GIT_CONFIG_COUNT=1 -e GIT_CONFIG_KEY_0=safe.directory -e GIT_CONFIG_VALUE_0='*' \
  "$image" git /repo --no-banner --redact --verbose --exit-code 1 \
  >gitleaks.log 2>&1 || rc=$?
cat gitleaks.log

# gitleaks exits 0 on an empty directory ("0 commits scanned", no leaks found), so a broken mount
# would look like a pass. Refuse that answer.
commits="$(git rev-list --count HEAD)"
if [ "$commits" -gt 0 ] && grep -Eq '(^|[^0-9])0 commits scanned' gitleaks.log; then
  echo "gitleaks scanned 0 of the $commits commits: the checkout never reached the container" >&2
  exit 1
fi
exit "$rc"
