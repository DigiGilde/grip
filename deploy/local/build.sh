#!/bin/sh
# Build the grip images for the local environment.
#
#   ./build.sh            from the working tree
#   ./build.sh head       from the last commit, with the container files
#                         (Dockerfile, entrypoint, nginx template) of the
#                         working tree. Use this while the working tree is
#                         in the middle of a change and does not build.
set -eu

here="$(cd "$(dirname "$0")" && pwd)"
repo="$(cd "$here/../.." && pwd)"
mode="${1:-tree}"

case "$mode" in
    tree)
        backend_ctx="$repo/backend"
        frontend_ctx="$repo/frontend"
        ;;
    head)
        src="$here/state/src"
        rm -rf "$src"
        mkdir -p "$src"
        git -C "$repo" archive HEAD backend frontend | tar -x -C "$src"
        cp "$repo/backend/Dockerfile" "$repo/backend/entrypoint.sh" "$src/backend/"
        cp "$repo/frontend/Dockerfile" "$repo/frontend/nginx.conf.template" "$src/frontend/"
        backend_ctx="$src/backend"
        frontend_ctx="$src/frontend"
        ;;
    *)
        echo "usage: $0 [tree|head]" >&2
        exit 64
        ;;
esac

sha="$(git -C "$repo" rev-parse --short HEAD 2>/dev/null || echo unknown)"
docker build -t grip-local/backend --build-arg GIT_SHA="$sha" "$backend_ctx"
docker build -t grip-local/frontend "$frontend_ctx"
# The ontwikkelportaal only holds docs and the site generator, so the working tree is enough.
docker build -t grip-local/ontwikkelportaal -f "$repo/ontwikkelportaal/Dockerfile" "$repo"
