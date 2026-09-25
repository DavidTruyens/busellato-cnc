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
if [[ ! "$disk_id" =~ ^[DH][0-9]{2}$ ]]; then
  echo "error: ID must look like D01 or H01, got '$disk_id'" >&2
  exit 1
fi
dir="${DISKS_DIR:-$repo/disks}/$disk_id"
img="$dir/$disk_id.img"
map="$dir/$disk_id.map"

# Resuming only makes sense for an unfinished read of the same disk.
# Anything else is most likely the wrong ID and would mix two disks.
if [[ -f "$img" && ! -f "$map" ]]; then
  echo "error: $img exists without a map; refusing to overwrite it" >&2
  exit 1
fi
if [[ -f "$map" && "$(python3 "$here/diskimg.py" bad-bytes "$map")" == 0 ]]; then
  echo "error: $disk_id is already captured completely. Wrong ID?" >&2
  echo "       To reprocess the image: tools/extract-disk.sh $disk_id \"label\" N" >&2
  exit 1
fi
if [[ -f "$map" ]]; then
  echo "Resuming the unfinished read of $disk_id: make sure the SAME diskette is inserted." >&2
fi
mkdir -p "$dir"

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
# -s caps the read at one 1.44 MB diskette, whatever SOURCE is.
run ddrescue -n -b 512 -s 1474560 "$src" "$img" "$map"
run ddrescue -r3 -b 512 -s 1474560 "$src" "$img" "$map"
if [[ ! -f "$src" ]]; then
  sudo chown "$(id -u):$(id -g)" "$img" "$map"
fi

exec "$here/extract-disk.sh" "$disk_id" "$label" "$expected"
