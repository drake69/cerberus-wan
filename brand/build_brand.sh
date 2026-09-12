#!/usr/bin/env bash
# Render the brand PNGs from the SVG sources.
#
# The PNGs are generated, never edited: change brand/cerberus.svg or
# brand/cerberus-dark.svg and run this. Sizes and the transparent background
# are what the Home Assistant brands repository asks for, and HACS looks for
# the files under custom_components/cerberus_wan/brand/.
#
# Needs rsvg-convert (librsvg) and ImageMagick.
set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
out="$here/../custom_components/cerberus_wan/brand"
mkdir -p "$out"

render() {
  local src="$1" name="$2" size="$3"
  rsvg-convert -w 2048 -h 2048 "$src" -o "$out/.raw.png"
  magick "$out/.raw.png" -trim +repage \
    -resize "${size}x${size}" \
    -background none -gravity center -extent "${size}x${size}" \
    -strip -define png:compression-level=9 "$out/$name"
  rm -f "$out/.raw.png"
}

render "$here/cerberus.svg"      icon.png          256
render "$here/cerberus.svg"      icon@2x.png       512
render "$here/cerberus-dark.svg" dark_icon.png     256
render "$here/cerberus-dark.svg" dark_icon@2x.png  512

echo "written to $out:"
cd "$out" && ls -l *.png | awk '{print "  " $9 "  " $5 " bytes"}'
