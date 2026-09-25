# D04 — recovered deleted files

The label says "4 bestanden", but all four directory entries on this
diskette are **deleted** (first byte `0xE5`, FAT cleared). Each file is
smaller than one 512-byte cluster, and its data sector was never
overwritten, so the contents are complete.

DOS overwrites the first letter of a deleted name. The full names come
from `disks/D14/files/PTPSYS/` (blue "PARAMETERS CNC", 2001), which holds
files with the same names and sizes. `OPTSYS.PAR` is byte-identical to
D14's copy; the other three differ, so this diskette is an older snapshot
of `C:\PTPSYS\`.

| Recovered as | Deleted entry | Bytes | DOS date | Cluster | Data at |
|---|---|---|---|---|---|
| `TAMP.DAT` | `\xE5AMP.DAT` | 256 | 1994-10-05 14:02 | 2 | sector 33 |
| `CONFSYS.PAR` | `\xE5ONFSYS.PAR` | 163 | 1993-05-11 10:00 | 3 | sector 34 |
| `OPTMOD.PAR` | `\xE5PTMOD.PAR` | 272 | 1992-07-23 13:46 | 4 | sector 35 |
| `OPTSYS.PAR` | `\xE5PTSYS.PAR` | 19 | 1992-07-22 17:22 | 5 | sector 36 |

Method: for each entry, read `size` bytes from sector `33 + cluster - 2`
of `D04.img` (1.44 MB layout: 1 boot + 2×9 FAT + 14 root-directory
sectors). `D04.img` itself is unchanged.
