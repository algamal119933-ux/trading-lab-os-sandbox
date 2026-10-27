# P3-PLN-05 — Portable-copy check and restore drill on the Windows PC (prepared, NOT_RUN)

**Authority:** [`P3_CONTRACT.md`](P3_CONTRACT.md) §3 PLN-05 (frozen at fcd06b21), executed under
[`OWNER_P3_EXECUTION_AUTHORIZATION.md`](OWNER_P3_EXECUTION_AUTHORIZATION.md) (7b1b1fa1). Decisions:
[`PLN_05_DESTINATION_DECISIONS.md`](PLN_05_DESTINATION_DECISIONS.md) §1–§2.
PAPER / RESEARCH ONLY · REAL_MONEY_AUTHORIZED = NO

```text
PORTABLE_COPY_INTEGRITY (Windows)  = NOT_RUN
PORTABLE_COPY_MATCHES_SET (§3.8)   = NOT_RUN
PORTABLE_COPY_RESTORE_DRILL        = NOT_RUN
HOST_LOSS_REDUNDANCY               = NOT_PROVEN   (neither result above can change it; see the decisions record §4)
```

This is a procedure for the Owner. Claude has no access to the Windows PC, the Toshiba disk or the host, and ran
nothing. Every result below is a template until the Owner attaches real output.

## 1. What it proves, and what it does not
| Level | What it proves | What it does not prove |
|---|---|---|
| **1. Integrity check, in place** (default) | The copy of set `20261026T033318Z` on the Toshiba disk is complete and every artifact re-hashes to the set's own `SHA256SUMS`, which matches the digest pinned in `BACKUP_RECORD.json`. Run with step 3.8 (or the narrower 3.6), it also proves the copy is the same set as the original on the WDC | That the archives extract, that the git bundle is valid, or that the runtime starts |
| **2. Restore drill in WSL** (optional, Owner approval per run) | The `scripts/p3/backup.py drill` checks on the copy: each root restores byte-identical to its manifest, sealed archives are ARCHIVE_VERIFIED, the git bundle clones with fsck clean and the recorded HEAD present | The config-load leg, unless Docker is available inside WSL. Without Docker it is recorded `NOT_RUN`, never PASS |

Neither level is Tier-3 evidence. Both are evidence about one portable, point-in-time set.

## 2. Rules for every run
1. **No effect on the live TLOS runtime.** The drill runs on the Windows PC only. The Toshiba disk is not attached
   to `hamza-workstation` during it, and nothing connects to the workstation. The disk is not a dependency of any
   TLOS timer or health check (decisions record §1), so its absence there raises nothing.
2. **The disk is read only.** Use only commands that read: `Get-FileHash`, `Get-Content`, `Get-ChildItem`,
   `Get-Volume`, `sha256sum`, `tar -x` **from** the disk. Never write, rename or delete anything on it. Do not
   regenerate `SHA256SUMS` or `BACKUP_RECORD.json`. Do not open the set in Explorer or previewers.
   Windows itself may write to a connected NTFS/exFAT volume outside this procedure's control: a
   `System Volume Information` or `$RECYCLE.BIN` folder at the volume root, indexing, or last-access metadata.
   None of these is inside the set folder, and the checks below cover the set folder only (`extra = 0` catches a
   `Thumbs.db` or `desktop.ini` written *inside* it). Detach with **Safely Remove Hardware**. This is a recorded
   residual of using Windows at all, not a step the drill takes.
3. **No disk-level changes, ever.** If Windows offers to "scan and fix" or says "You need to format the disk",
   choose **Cancel**. Do not use Disk Management or `diskpart`, including `attributes … readonly`, because that
   writes partition metadata. A format prompt usually means the disk holds a Linux (ext4) file system that Windows
   cannot read: Level 1 then runs only through WSL (§3.7), or it is recorded `NOT_RUN`.
4. **No permanent copy on the PC.** Level 1 copies nothing; it reads in place. Its only output is a small text
   report of file names and hashes, with no file contents, in `%TEMP%`. Level 2 writes a temporary scratch restore
   and deletes it at the end (§4). A permanent copy needs a separate Owner approval, which the Owner has declined.
5. **Secrets.** The set holds the runtime `.env` and `config.json`, the Grafana, MLflow and Prometheus volumes,
   the git bundle and Claude memory files. Level 1 never extracts anything, so no secret is exposed; its report and
   the §3.8 export hash the set's *artifacts* (archives, manifests, bundles, volume tars), never a file inside
   an archive. Level 2
   extracts them into scratch: never print, `cat`, open, copy or paste any restored `.env`, `config.json` or
   volume content, and never attach the scratch tree to a chat. The reports contain names and hashes only. If any
   file in the set holds a private exchange key, that is a paper-boundary violation to report, not to use.
6. **Original manifests preserved.** The check hashes `SHA256SUMS` and `BACKUP_RECORD.json` before and after the
   run. The run is valid only if both hashes are unchanged.
7. **No installation.** If WSL, `git`, Python or Docker is absent, the dependent step is `NOT_RUN`. Installing any
   of them is a change to that computer and needs explicit Owner authorization.

## 3. Level 1 — integrity check in place (Windows PowerShell, built-in tools only)
Uses only `Get-FileHash`, `Get-Content`, `ConvertFrom-Json` and `Get-ChildItem`, which ship with Windows
PowerShell 5.1 and PowerShell 7. WSL is not needed. It mirrors `backup.verify_backup`:
- the `SHA256SUMS` digest must equal `BACKUP_RECORD.json` `sha256sums_digest`;
- every listed artifact must exist and re-hash equal.

It adds three checks:
- the listed count must equal `2 × roots + repos + volumes` from `BACKUP_RECORD.json`, which is exactly what
  `backup.create_backup` lists;
- the copy holds no unlisted file;
- the two manifests are unchanged after the run.

3.1 Connect the Toshiba disk to the PC. Note its drive letter and the folder that holds the set.
3.2 Open **Windows PowerShell** as the normal user, not as Administrator. Paste the block below, after setting
`$set` to the real path. Pasted commands are not subject to the script execution policy, so no policy change is
needed.

```powershell
# TLOS portable-copy integrity check — read-only. Nothing is written to the disk.
$ErrorActionPreference = 'Stop'
$set   = 'E:\tlos-backups\20261026T033318Z'   # <-- the Owner sets the real drive letter and folder
$stamp = (Get-Date).ToUniversalTime().ToString('yyyyMMddTHHmmssZ')
$out   = Join-Path $env:TEMP "tlos-pcd-$stamp.txt"
if (Test-Path -LiteralPath $out) { throw "STOP: $out exists" }
$log = New-Object System.Collections.Generic.List[string]
function Say([string]$s) { $log.Add($s); Write-Output $s }
function H([string]$p) { (Get-FileHash -LiteralPath $p -Algorithm SHA256).Hash.ToLower() }

Say 'PCD_VERSION = TLOS_PORTABLE_COPY_CHECK_V1'
Say "utc = $stamp  computer = $env:COMPUTERNAME  powershell = $($PSVersionTable.PSVersion)"
$letter = (Get-Item -LiteralPath $set).PSDrive.Name
Get-Volume -DriveLetter $letter | ForEach-Object {
  Say "volume = ${letter}: fs=$($_.FileSystemType) label=$($_.FileSystemLabel) size=$($_.Size) free=$($_.SizeRemaining)" }
Say "set = $set"

$sums = Join-Path $set 'SHA256SUMS'; $rec = Join-Path $set 'BACKUP_RECORD.json'
$sumsBefore = H $sums; $recBefore = H $rec
$record = Get-Content -LiteralPath $rec -Raw | ConvertFrom-Json
Say "record_stamp = $($record.stamp)"
Say "sha256(SHA256SUMS) = $sumsBefore"
Say "sha256(BACKUP_RECORD.json) = $recBefore"
$digestOk = ($sumsBefore -eq $record.sha256sums_digest)
Say "record_digest_match = $digestOk"

$expected = 2 * @($record.roots.PSObject.Properties).Count + @($record.repos.PSObject.Properties).Count + @($record.volumes).Count
$lines = @(Get-Content -LiteralPath $sums | Where-Object { $_.Length -gt 66 })
$ok = 0; $bad = @(); $missing = @(); $listed = @{}
foreach ($line in $lines) {
  $want = $line.Substring(0, 64); $rel = $line.Substring(66); $listed[$rel] = $true
  $p = Join-Path $set ($rel -replace '/', '\')
  if (-not (Test-Path -LiteralPath $p -PathType Leaf)) { $missing += $rel; Say "MISSING  $rel"; continue }
  $got = H $p
  if ($got -eq $want) { $ok++; Say "OK       $got  $rel" } else { $bad += $rel; Say "MISMATCH $got  $rel (expected $want)" }
}
$root = (Get-Item -LiteralPath $set).FullName.TrimEnd('\')
$extra = @(Get-ChildItem -LiteralPath $set -Recurse -File -Force | ForEach-Object {
  $_.FullName.Substring($root.Length + 1) -replace '\\', '/' } |
  Where-Object { -not $listed.ContainsKey($_) -and $_ -ne 'SHA256SUMS' -and $_ -ne 'BACKUP_RECORD.json' })
foreach ($e in $extra) { Say "EXTRA    $e" }

$unchanged = ((H $sums) -eq $sumsBefore) -and ((H $rec) -eq $recBefore)
Say "listed = $($lines.Count)  expected_from_record = $expected  ok = $ok  mismatched = $($bad.Count)  missing = $($missing.Count)  extra = $($extra.Count)"
Say "manifests_unchanged = $unchanged"
$pass = $digestOk -and $lines.Count -gt 0 -and $lines.Count -eq $expected -and $ok -eq $lines.Count -and
        $bad.Count -eq 0 -and $missing.Count -eq 0 -and $extra.Count -eq 0 -and $unchanged
Say ("PORTABLE_COPY_INTEGRITY = " + $(if ($pass) { 'PASS' } else { 'FAIL' }))
$log | Set-Content -LiteralPath $out -Encoding UTF8
Write-Output "report = $out  sha256 = $(H $out)"
```

3.3 **PASS** requires every one of these, all printed in the report:
- `record_digest_match = True`;
- `listed` > 0 and `listed = expected_from_record`. For a set written by `scripts/p3/scheduled_backup.sh` as
  configured on main, that is **14**: 5 roots × 2, plus 1 bundle, plus 3 volumes. The record decides, not this
  number;
- `ok = listed`, and `mismatched = 0`, `missing = 0`, `extra = 0`;
- `manifests_unchanged = True`;
- the last line reads `PORTABLE_COPY_INTEGRITY = PASS`.

Anything else is **FAIL** and is recorded as it is. A FAIL means the portable copy is not trusted. It says nothing
about the original set on the WDC.

3.4 Duration: about 1 GB of reads over USB, typically a few minutes.

3.5 **Evidence to attach:** the full report text, plus the `report = … sha256 = …` line. The report holds names and
hashes only. After attaching it, delete it and show that it is gone:
```powershell
Remove-Item -LiteralPath $out; "REPORT_REMOVED = " + (-not (Test-Path -LiteralPath $out))
```

3.6 **Optional cross-check against the original.** This proves the copy *is* the original set, not only a
self-consistent one. It is read-only on the host, but it runs on `hamza-workstation`, so it needs the Owner's own
go-ahead:
```bash
sha256sum /mnt/tlos-wdc/tlos-backups/20261026T033318Z/SHA256SUMS /mnt/tlos-wdc/tlos-backups/20261026T033318Z/BACKUP_RECORD.json
```
**MATCH** means both hashes equal the `sha256(SHA256SUMS)` and `sha256(BACKUP_RECORD.json)` lines of the Windows
report.

3.7 **WSL variant**, only if WSL is already installed. Use it when the disk is ext4, or as a second, independent
implementation.

For an NTFS or exFAT disk, mount it read-only inside WSL:
```bash
sudo mkdir -p /mnt/tlos-ro && sudo mount -t drvfs E: /mnt/tlos-ro -o ro
findmnt -no OPTIONS /mnt/tlos-ro | tr ',' '\n' | grep -qx ro && echo MOUNT_RO=YES || { echo "MOUNT_RO=NO: STOP"; sudo umount /mnt/tlos-ro; }
```
For an ext4 disk, run this from an **Administrator** PowerShell:
`wsl --mount \\.\PHYSICALDRIVE<N> --partition <P> --type ext4 --options ro`. Find `<N>` with
`Get-CimInstance Win32_DiskDrive`; this only reads. The disk then appears under `/mnt/wsl/PHYSICALDRIVE<N>p<P>`.
Afterwards run `wsl --unmount \\.\PHYSICALDRIVE<N>` (ext4), or `sudo umount /mnt/tlos-ro` (drvfs), and confirm with
`findmnt /mnt/tlos-ro || echo UNMOUNTED=YES`.

Then, from the set directory:
```bash
s=/mnt/tlos-ro/<folder>/20261026T033318Z
cd "$s" && sha256sum SHA256SUMS BACKUP_RECORD.json \
  && python3 -c "import json;print('record digest', json.load(open('BACKUP_RECORD.json'))['sha256sums_digest'])" \
  && sha256sum -c --strict SHA256SUMS; echo "sha256sum_exit=$?"
```
PASS: the `SHA256SUMS` hash equals the record digest, every line prints `OK`, and `sha256sum_exit=0`. This does
not count lines or extras; the PowerShell report covers those.

3.8 **Second implementation, against the original (recommended; supersedes 3.6, which remains for when no CSV can be carried).** The PowerShell check above is
the only implementation of the rules that runs on the PC. This step moves the judgement into the repository's
own tested code (`backup.compare_hash_export`, which applies `verify_backup`'s rules and adds the copy checks:
manifests byte-identical to the original's, count from the record, no unlisted file). On the PC, in the same
PowerShell window (read-only on the disk; one CSV of names and hashes is written to `%TEMP%`):
```powershell
$csv = Join-Path $env:TEMP "tlos-pcd-hashes-$stamp.csv"
Get-ChildItem -LiteralPath $set -Recurse -File -Force | Get-FileHash -Algorithm SHA256 |
  Export-Csv -LiteralPath $csv -NoTypeInformation -Encoding UTF8
Write-Output "export = $csv  sha256 = $(H $csv)  root = $set"
```
Carry the CSV (names and hashes only, no secret) to `hamza-workstation`. With the Owner's go-ahead, because it
runs on the host, though it only reads:
```bash
python3 scripts/p3/backup.py compare-export --set /mnt/tlos-wdc/tlos-backups/20261026T033318Z \
  --export ~/tlos-pcd-hashes.csv --export-root 'E:\tlos-backups\20261026T033318Z' --json ~/tlos-pcd-compare.json
echo "compare_exit=$?"
```
`--export-root` is the `$set` value exactly as printed on the PC. **PASS:** `compare_exit=0` and
`PORTABLE_COPY_MATCHES_SET = PASS`. Exit 1 is FAIL; exit 2 is UNPROVEN (an unreadable or empty export, or an
unreadable set), which withholds PASS exactly as FAIL does. Then delete the CSV on the PC
(`Remove-Item -LiteralPath $csv; "CSV_REMOVED = " + (-not (Test-Path -LiteralPath $csv))`). The same command can
be run by a second party, Claude included, from the attached CSV and the original set's `SHA256SUMS` and
`BACKUP_RECORD.json` in a scratch folder; it then proves the copy matches those two manifests.

## 4. Level 2 — restore drill in WSL (optional; the Owner approves each run)
Prerequisites, all already present. None is installed by this procedure:
- WSL with `python3`, `git`, and `tar` with zstd support;
- a checkout of this repository at a named main SHA, so the drill code is not taken from the set it tests;
- about 3 GB free on the WSL disk for the scratch.

```bash
umask 077                       # the restore holds .env and config.json: owner-only while it exists
repo=~/tlos-drill-code          # an existing checkout at a named main SHA; record it:
git -C "$repo" rev-parse HEAD
s=/mnt/tlos-ro/<folder>/20261026T033318Z       # the read-only mount from §3.7
scratch=~/tlos-pcd-scratch-$(date -u +%Y%m%dT%H%M%SZ); [ -e "$scratch" ] && echo STOP || mkdir "$scratch"
(cd "$repo" && python3 scripts/p3/backup.py verify --set "$s"); echo "verify_exit=$?"
(cd "$repo" && python3 scripts/p3/backup.py drill --set "$s" --scratch "$scratch/restore" --json "$scratch/drill.json"); echo "drill_exit=$?"
sha256sum "$scratch/drill.json"; cp "$scratch/drill.json" ~/tlos-pcd-drill-$(basename "$scratch").json
chmod -R u+rwX -- "$scratch"    # a restored read-only or mode-000 directory must not survive the delete
rm -rf -- "$scratch"; [ -e "$scratch" ] && echo "SCRATCH_REMOVED=NO" || echo "SCRATCH_REMOVED=YES"
```

**`--config-load` is omitted.** It needs Docker and the pinned Freqtrade image inside WSL. Without them the
config-load leg is recorded `NOT_RUN`. With them it may be added as `--config-load trading/trading_lab_os_final`,
which issues only `list-strategies` and `show-config`, with `--network none`.

**PASS requires:**
- `verify_exit=0` and `drill_exit=0`;
- `drill.json` shows every check PASS: `backup_integrity`, each `root:*`, each `sealed:*`, and `git:trading_lab_os_final`;
- `PLN_03_RESTORE_DRILL = PASS`;
- `SCRATCH_REMOVED=YES`.

The kept `drill.json` holds check names, counts and differing file names, and no file contents. After attaching
it, delete it and show that it is gone: `rm -f -- ~/tlos-pcd-drill-*.json; ls ~/tlos-pcd-drill-*.json 2>/dev/null
|| echo DRILL_JSON_REMOVED=YES`.

**Residual data:** deleting the scratch frees its blocks inside the WSL virtual disk, but does not overwrite them.
If that is unacceptable, do not run Level 2: Level 1 alone needs no extraction.

## 4a. Pass/fail summary (every condition is a printed line, not a judgement)
| Result | PASS only if | Otherwise |
|---|---|---|
| `PORTABLE_COPY_INTEGRITY` | `record_digest_match = True` · `listed = expected_from_record` > 0 · `ok = listed` · `mismatched = missing = extra = 0` · `manifests_unchanged = True` · `REPORT_REMOVED = True` | FAIL |
| `PORTABLE_COPY_MATCHES_SET` | `compare_exit=0` and `PORTABLE_COPY_MATCHES_SET = PASS` · `CSV_REMOVED = True` | exit 1 FAIL · exit 2 UNPROVEN · not run NOT_RUN |
| WSL read-only mount (if used) | `MOUNT_RO=YES` before, `UNMOUNTED=YES` after | STOP; the run is void |
| `PORTABLE_COPY_RESTORE_DRILL` | `verify_exit=0` · `drill_exit=0` · `PLN_03_RESTORE_DRILL = PASS` · `SCRATCH_REMOVED=YES` · `DRILL_JSON_REMOVED=YES` after attaching | FAIL, or NOT_RUN |
| No permanent copy on the PC | `REPORT_REMOVED`, `CSV_REMOVED`, `SCRATCH_REMOVED`, `DRILL_JSON_REMOVED` all true | the residue is named in the record |

## 5. Record template (fill only from attached output)
```text
PORTABLE_COPY_SET          20261026T033318Z on the Toshiba MQ04UBD200 (fs <…>, drive <…>)
PC                         <COMPUTERNAME> (Owner-confirmed: YES/NO)
LEVEL_1                    report sha256 <…>; listed <n> = expected <n>; ok <n>; mismatched 0; missing 0; extra 0;
                           manifests_unchanged True → PORTABLE_COPY_INTEGRITY = PASS/FAIL     [OWNER-ATTACHED]
CROSS_CHECK_WDC            sha256(SHA256SUMS) <…> / sha256(BACKUP_RECORD.json) <…> MATCH/DIFFER / NOT_RUN
COMPARE_EXPORT (§3.8)      export sha256 <…>; code at <sha>; compare_exit <n> → PORTABLE_COPY_MATCHES_SET = PASS/FAIL/UNPROVEN / NOT_RUN
PC_RESIDUE                 REPORT_REMOVED / CSV_REMOVED / SCRATCH_REMOVED / DRILL_JSON_REMOVED = <True/YES …>
LEVEL_2                    code at <sha>; drill.json sha256 <…>; checks <…> PASS; config_load NOT_RUN;
                           scratch removed YES → PORTABLE_COPY_RESTORE_DRILL = PASS/FAIL / NOT_RUN
HOST_LOSS_REDUNDANCY       NOT_PROVEN (unchanged by any of the above)
```
