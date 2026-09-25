#!/usr/bin/env bash
# Extract files from disks/<ID>/<ID>.img and print its index row.
#
#   tools/extract-disk.sh ID "label text" EXPECTED_FILE_COUNT
#
# Writes <ID>/files/ and <ID>/<ID>.dir.txt. Never modifies <ID>.img.
# Exit: 0 clean, 3 count mismatch or bad sectors, 2 unrecognised image,
# 1 usage/missing image. DISKS_DIR overrides <repo>/disks (tests).
set -euo pipefail

here="$(cd "$(dirname "$0")" && pwd)"
repo="$(dirname "$here")"

if [[ $# -ne 3 ]]; then
  echo "usage: $0 ID \"label text\" EXPECTED_FILE_COUNT" >&2
  exit 1
fi
disk_id="$1"; label="$2"; expected="$3"
if [[ ! "$disk_id" =~ ^[DH][0-9]{2}$ ]]; then
  echo "error: ID must look like D01 or H01, got '$disk_id'" >&2
  exit 1
fi
dir="${DISKS_DIR:-$repo/disks}/$disk_id"
img="$dir/$disk_id.img"
map="$dir/$disk_id.map"

if [[ ! -f "$img" ]]; then
  echo "error: $img not found" >&2
  exit 1
fi

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
work="$tmp/work.img"

# Fails with exit 2 before anything in $dir is touched.
boot="$(python3 "$here/diskimg.py" work "$img" "$work")" || exit 2

mdir -i "$work" -/ -a '::' > "$dir/$disk_id.dir.txt" 2>&1 || true

# A damaged FAT or directory makes mcopy stop part-way. Keep what was
# copied and still report, so a failing disk never goes unnoticed.
rm -rf "$dir/files"
mkdir "$dir/files"
copy_failed=0
if [[ -n "$(mdir -i "$work" -b '::' 2>/dev/null || true)" ]]; then
  mcopy -i "$work" -s -m -n '::/*' "$dir/files/" || copy_failed=1
fi

found="$(find "$dir/files" -type f -not -path '*/System Volume Information/*' | wc -l | tr -d ' ')"

if [[ -f "$map" ]]; then
  bad_b="$(python3 "$here/diskimg.py" bad-bytes "$map")"
  bad=$(( (bad_b + 511) / 512 ))
  imaged="$(grep -m1 '^# Start time:' "$map" | awk '{print $4}' || true)"
else
  bad="no map"
  imaged=""
fi
[[ -n "$imaged" ]] || imaged="$(date +%Y-%m-%d)"

sha="$(shasum -a 256 "$img" | cut -d' ' -f1)"
[[ "$boot" == ok ]] && boot_col="OK" || boot_col="substituted"

status=0
count="$expected / $found"
if [[ "$found" != "$expected" ]]; then
  count="$count ⚠"
  status=3
fi
if [[ "$bad" != 0 && "$bad" != "no map" ]]; then
  status=3
fi
if [[ "$copy_failed" == 1 ]]; then
  count="$count, extraction failed ⚠"
  status=3
fi

echo "| $disk_id | $label | $imaged | \`$sha\` | $bad | $count | $boot_col | |"
echo "$disk_id: $found files (expected $expected), bad sectors: $bad, boot sector: $boot_col" >&2
exit "$status"
