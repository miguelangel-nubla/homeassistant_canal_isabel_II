#!/bin/sh
# Start a release: prepare it as a draft and push its tag. The workflow
# "Session helper image" tests and builds the helper image of that version
# and only then publishes the release and updates the add-on repository.
#
#   dev/release.sh v2026.11.10 notes.md          a release
#   dev/release.sh v2026.11.10-rc.1 notes.md     a pre-release (not offered as an update)
#
# The notes file is what people read on the release page.
set -eu
TAG="${1:?usage: dev/release.sh v<version> <notes file>}"
NOTES="${2:?usage: dev/release.sh v<version> <notes file>}"
cd "$(dirname "$0")/.."

case "$TAG" in v[0-9]*) ;; *) echo "The tag must look like v2026.11.10" >&2; exit 1 ;; esac
[ -s "$NOTES" ] || { echo "No notes in $NOTES" >&2; exit 1; }
git fetch -q origin main --tags
[ "$(git rev-parse HEAD)" = "$(git rev-parse origin/main)" ] || { echo "Release from an up-to-date main" >&2; exit 1; }
git rev-parse -q --verify "refs/tags/$TAG" >/dev/null && { echo "The tag $TAG already exists" >&2; exit 1; }

VERSION="${TAG#v}"
MANIFEST=$(sed -n 's/.*"version": "\(.*\)".*/\1/p' custom_components/canal_de_isabel_ii/manifest.json)
case "$TAG" in
    *-*) PRERELEASE="--prerelease"
         [ "${VERSION%%-*}" = "$MANIFEST" ] || { echo "manifest.json says $MANIFEST, the tag ${VERSION%%-*}" >&2; exit 1; } ;;
    *)   PRERELEASE=""
         [ "$VERSION" = "$MANIFEST" ] || { echo "manifest.json says $MANIFEST, the tag $VERSION" >&2; exit 1; } ;;
esac

# shellcheck disable=SC2086
gh release create "$TAG" --draft $PRERELEASE --target main --title "$TAG" --notes-file "$NOTES" >/dev/null
git tag "$TAG" origin/main
git push -q origin "$TAG"
echo "Draft of $TAG created and tag pushed. It is published when its image is built:"
echo "  gh run watch \$(gh run list --workflow session-helper.yml --branch $TAG --limit 1 --json databaseId --jq '.[0].databaseId')"
