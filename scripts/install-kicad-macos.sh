#!/usr/bin/env bash
# Install KiCad <version> from its universal disk image into $RUNNER_TEMP and
# hand its Python and kicad-cli's directory to later workflow steps.
set -euo pipefail

version=${1:?usage: install-kicad-macos.sh <version>}
if ! [[ $version =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
    echo "not a KiCad version: $version" >&2
    exit 2
fi
temp=${RUNNER_TEMP:?RUNNER_TEMP is not set}
image="$temp/kicad-$version.dmg"
mount="$temp/kicad-dmg"
url="https://github.com/KiCad/kicad-source-mirror/releases/download/$version/kicad-unified-universal-$version.dmg"

curl --fail --silent --show-error --location --retry 3 --output "$image" "$url"
mkdir -p "$mount"
hdiutil attach -nobrowse -readonly -noverify -mountpoint "$mount" "$image" > /dev/null
trap 'hdiutil detach "$mount" > /dev/null || true' EXIT

# The image holds KiCad/KiCad.app beside the demos; insist on exactly one.
count=0
source_app=
while IFS= read -r found; do
    count=$((count + 1))
    source_app=$found
done < <(find "$mount" -maxdepth 3 -name KiCad.app -type d)
if [ "$count" -ne 1 ]; then
    echo "expected one KiCad.app in the KiCad $version image, found $count" >&2
    exit 1
fi

app="$temp/kicad/KiCad.app"
mkdir -p "$temp/kicad"
ditto "$source_app" "$app"
python="$app/Contents/Frameworks/Python.framework/Versions/Current/bin/python3"
if [ ! -x "$python" ]; then
    echo "no KiCad Python at $python" >&2
    exit 1
fi

echo "KICAD_PYTHON=$python" >> "$GITHUB_ENV"
echo "$app/Contents/MacOS" >> "$GITHUB_PATH"
echo "KiCad $version installed in $app"
