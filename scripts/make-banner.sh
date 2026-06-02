#!/bin/sh
# Regenerate docs/assets/banner.png from docs/assets/logo.svg (the single source
# of the cloche) plus the chefe wordmark. The README/PyPI need a raster banner;
# this keeps the mark defined once. macOS only (qlmanage + ImageMagick).
#   scripts/make-banner.sh
set -eu
root="$(cd "$(dirname "$0")/.." && pwd)"
mark="$(awk '/<g /{f=1;next} /<\/g>/{f=0} f' "$root/docs/assets/logo.svg")"
tmp="$(mktemp -d)"
cat > "$tmp/banner.svg" <<SVG
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1200 320" fill="none">
  <rect width="1200" height="320" rx="32" fill="#16161a"/>
  <rect x="3" y="3" width="1194" height="314" rx="30" fill="none" stroke="#eab308" stroke-width="2" opacity="0.5"/>
  <g transform="translate(58 64) scale(2)" stroke="#eab308" stroke-linecap="round" stroke-linejoin="round" fill="none" stroke-width="4">
$mark
  </g>
  <text x="320" y="165" font-family="'Space Grotesk','Helvetica Neue',Arial,sans-serif" font-weight="700" font-size="104" letter-spacing="-3" fill="#ffffff">chefe</text>
  <text x="325" y="220" font-family="'Space Grotesk','Helvetica Neue',Arial,sans-serif" font-weight="500" font-size="32" fill="#eab308">One manifest for every package manager</text>
</svg>
SVG
qlmanage -t -s 2400 -o "$tmp" "$tmp/banner.svg" >/dev/null 2>&1
magick "$tmp/banner.svg.png" -trim +repage "$tmp/content.png"
w="$(magick identify -format '%w' "$tmp/content.png")"
h="$(magick identify -format '%h' "$tmp/content.png")"
magick -size "${w}x${h}" xc:black -fill white \
  -draw "roundrectangle 0,0,$((w - 1)),$((h - 1)),64,64" "$tmp/mask.png"
magick "$tmp/content.png" "$tmp/mask.png" -alpha off -compose CopyOpacity -composite \
  "$root/docs/assets/banner.png"
rm -rf "$tmp"
echo "banner.png regenerated from logo.svg"
