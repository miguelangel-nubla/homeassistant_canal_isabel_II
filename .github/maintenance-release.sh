#!/bin/sh
# Make a maintenance release if Debian has a newer Chromium than the one in
# the image of the last release. Run by the workflow "Session helper image"
# once a month.
#
# Prints "tag=v<version>" when it has started a release (the version is
# bumped on main, the release prepared as a draft and its tag pushed), and
# nothing when there is no need. Everything else goes to standard error.
set -eu
: "${IMAGE:?}" "${GH_TOKEN:?}"

LAST=$(gh release list --exclude-drafts --exclude-pre-releases --limit 1 --json tagName --jq '.[0].tagName')
OLD=$(docker run --rm --entrypoint dpkg-query "$IMAGE:${LAST#v}" -W -f '${Version}' chromium)
NEW=$(docker run --rm debian:bookworm-slim sh -c \
    'apt-get update -qq >/dev/null 2>&1 && apt-cache policy chromium | sed -n "s/ *Candidate: //p"')
echo "Chromium in $LAST: $OLD. In Debian now: $NEW." >&2
if [ -z "$NEW" ] || [ "$OLD" = "$NEW" ]; then
    echo "Nothing to release." >&2
    exit 0
fi

MANIFEST=custom_components/canal_de_isabel_ii/manifest.json
CURRENT=$(sed -n 's/.*"version": "\(.*\)".*/\1/p' "$MANIFEST")
# Versions are YYYY.M.patch: the next patch of this month, or its first.
VERSION=$(python3 - "$CURRENT" <<'PY'
import datetime, sys
year, month, patch = (int(part) for part in sys.argv[1].split("."))
today = datetime.date.today()
print(f"{year}.{month}.{patch + 1}" if (year, month) == (today.year, today.month) else f"{today.year}.{today.month}.0")
PY
)
TAG="v$VERSION"
sed -i "s/\"version\": \"$CURRENT\"/\"version\": \"$VERSION\"/" "$MANIFEST"
git config user.name "github-actions[bot]"
git config user.email "41898282+github-actions[bot]@users.noreply.github.com"
git commit -q -am "chore: version $VERSION (session helper rebuilt with Chromium $NEW)" >&2
git push -q origin HEAD:main >&2

gh release create "$TAG" --draft --target main --title "$TAG" --notes "Maintenance release: the session helper's image is rebuilt with the current Chromium ($OLD → $NEW), so that the browser that logs in to the virtual office does not grow old.

No other changes. Update the session helper; the integration only changes its version number." >&2
git push -q origin "HEAD:refs/tags/$TAG" >&2
echo "Started the release $TAG." >&2
echo "tag=$TAG"
