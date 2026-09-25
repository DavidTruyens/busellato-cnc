#!/usr/bin/env bash
# Read one diskette into disks/<ID>/ with ddrescue, then extract it.
#
#   tools/image-disk.sh ID "label text" EXPECTED_FILE_COUNT [SOURCE]
#
# Lock the diskette's write-protect tab first. If macOS says the disk is
# not readable, click "Ignore" (never "Initialize").
# SOURCE defaults to the single attached 1.44 MB USB floppy (needs sudo).
# A regular file may be given instead; then no sudo or diskutil is used.
# Re-running resumes from the existing map; good sectors are not re-read.
set -euo pipefail

here="$(cd "$(dirname "$0")" && pwd)"
repo="$(dirname "$here")"

if [[ $# -lt 3 || $# -gt 4 ]]; then
  echo "usage: $0 ID \"label text\" EXPECTED_FILE_COUNT [SOURCE]" >&2
  exit 1
fi
disk_id="$1"; label="$2"; expected="$3"; src="${4:-}"
dir="${DISKS_DIR:-$repo/disks}/$disk_id"
mkdir -p "$dir"
img="$dir/$disk_id.img"
map="$dir/$disk_id.map"

if [[ -z "$src" ]]; then
  disk="$(diskutil list external physical | python3 "$here/diskimg.py" find-floppy)"
  echo "Using $disk" >&2
  diskutil unmountDisk "$disk" >/dev/null
  src="/dev/r${disk#/dev/}"
fi

run() {
  if [[ -f "$src" ]]; then "$@"; else sudo "$@"; fi
}

# Pass 1: everything, no retries. Pass 2: retry bad sectors up to 3 times.
run ddrescue -n -b 512 "$src" "$img" "$map"
run ddrescue -r3 -b 512 "$src" "$img" "$map"
if [[ ! -f "$src" ]]; then
  sudo chown "$(id -u):$(id -g)" "$img" "$map"
fi

exec "$here/extract-disk.sh" "$disk_id" "$label" "$expected"
