#!/bin/sh
# Render the brand images of the integration and of the session helper from
# the vector files in this folder. Needs rsvg-convert (brew install librsvg).
#   dev/brand/render.sh
set -eu
cd "$(dirname "$0")"
INTEGRATION=../../custom_components/canal_de_isabel_ii/brand
HELPER=../../canal-session-helper

# Home Assistant: square icons of 256 and 512, logos 256 and 512 high.
rsvg-convert -w 256 -h 256 icon.svg -o "$INTEGRATION/icon.png"
rsvg-convert -w 512 -h 512 icon.svg -o "$INTEGRATION/icon@2x.png"
rsvg-convert -h 256 logo.svg -o "$INTEGRATION/logo.png"
rsvg-convert -h 512 logo.svg -o "$INTEGRATION/logo@2x.png"
rsvg-convert -h 256 logo-dark.svg -o "$INTEGRATION/dark_logo.png"
rsvg-convert -h 512 logo-dark.svg -o "$INTEGRATION/dark_logo@2x.png"

# The app (add-on): a 128 icon and a logo about 250 wide.
rsvg-convert -w 128 -h 128 icon.svg -o "$HELPER/icon.png"
rsvg-convert -w 250 logo.svg -o "$HELPER/logo.png"
rsvg-convert -w 250 logo-dark.svg -o "$HELPER/dark_logo.png"
