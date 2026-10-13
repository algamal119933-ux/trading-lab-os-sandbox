#!/usr/bin/env python3
"""The readiness jobs' own steps, RT-1 to RT-11 (review section 4; Owner decisions OD-S2, OD-S5 and OD-S6).

    python -m auth2q2.harness restore  --address A --commit SHA --dest D --assets-dir R [--cache-dir C]
                                       [--refill-cache] [--expect-source cache|release] [--manifest-out M]
                                       --repo-slug O/R --out F
    python -m auth2q2.harness verify   --address A --manifest M --dest D --out F        (before every science phase)
    python -m auth2q2.harness d0       --repo . --cache D --out F                       (science, network removed)
    python -m auth2q2.harness engine   --repo . --cache D --work W --out F              (science, network removed)
    python -m auth2q2.harness corrupt  --address A --manifest M --dest D --out F        (RT-6)
    python -m auth2q2.harness tamper   --assets-dir R --out F                           (RT-6)
    python -m auth2q2.harness classify --test RT-6|RT-7|RT-10 --repo-slug O/R --run-id N [--expect F] --out F
    python -m auth2q2.harness prep-check --record F --repo .                       (RT-1, before publishing)
    python -m auth2q2.harness compare-release --dir OUT --commit SHA --repo . --repo-slug O/R --out F  (RT-2)
    python -m auth2q2.harness verdict  --test RT-n --job NAME --repo . --out F IN...
    python -m auth2q2.harness fail     --test RT-n --job NAME --reason TEXT --out F    (a test that did not finish)

Restore. The snapshot comes from the Actions cache when the cache holds it whole (this run's own entry), else from
the readiness commit's immutable release (release.py: one per snapshot address and readiness commit), and either way every file is checked against the manifest at the snapshot's address before anything
reads it. The cache is only an accelerator: a missing or broken cache entry falls back to the release, and the
receipt says why. Release assets are checked against GitHub's digests when they are downloaded and again right
before they are unpacked, so an asset changed in between (RT-6) stops the restore and is named.

Science. ``d0`` and ``engine`` run inside the workflow's network namespace (offline.py) and refuse to start
unless the network is gone; the archive listing is replayed from the snapshot (listing.py) and every socket call
is refused in-process too. ``d0`` rebuilds Dataset V3 and compares it with the committed lock byte for byte, as
run_node.d0 does (RT-4); ``engine`` makes run_node.real_market's DATA_TRUTH check for A2, every 4h and funding
hash against the lock (RT-11). Neither runs a strategy, a signal or an engine: they rebuild data and compare
hashes. Nothing here writes the repository, a ledger or a release.

Each test's verdict is one result record (RESULT_SCHEMA), PASS only if every one of its checks holds; the job
publishes it as an annotation (.github/gates/auth2q2_readiness.py annotate), which the readiness record reads.

PAPER / RESEARCH ONLY.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

_HERE = Path(__file__).resolve().parent
if str(_HERE.parent) not in sys.path:
    sys.path.insert(0, str(_HERE.parent))

from auth2 import archive as A  # noqa: E402
from auth2 import dataset_v3 as D  # noqa: E402
from auth2q2 import attempts as AT  # noqa: E402
from auth2q2 import listing as L  # noqa: E402
from auth2q2 import offline as OFF  # noqa: E402
from auth2q2 import plan as PL  # noqa: E402
from auth2q2 import release as RL  # noqa: E402
from auth2q2 import snapshot as SN  # noqa: E402

RECEIPT_SCHEMA = "AUTH2Q2_RESTORE_RECEIPT_1"
RESULT_SCHEMA = "AUTH2Q2_READINESS_RESULT_1"
CACHE, RELEASE = "cache", "release"
CACHE_MISS, CACHE_INVALID = "CACHE_MISS", "CACHE_INVALID"
RESTORE_STEP = "Restore the snapshot"
VERIFY_STEP = "Verify the snapshot before science"
INFRA_STEP = "Infrastructure phase (probe)"
ENGINE_FAMILY = "A2"
SETTLE_TRIES, SETTLE_SECONDS = 6, 10   # a classifier waits at most a minute for the API to show the probes ended


class HarnessError(Exception):
    """A readiness step could not do what it must. Fail closed."""


def now_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def write_json(path: Path, obj) -> str:
    body = json.dumps(obj, indent=1, sort_keys=True, ensure_ascii=False) + "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    return body


def read_json(path: Path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def run_env() -> dict:
    return {"run_id": os.environ.get("GITHUB_RUN_ID"), "run_attempt": os.environ.get("GITHUB_RUN_ATTEMPT"),
            "sha": os.environ.get("GITHUB_SHA")}


def result(test: str, job: str, checks: dict[str, bool], measurements: dict | None = None,
           problems: list[str] | None = None) -> dict:
    """A test's verdict: PASS only if every check is exactly True and nothing went wrong."""
    problems = list(problems or [])
    problems += [f"check failed: {k}" for k, v in sorted(checks.items()) if v is not True]
    if not checks:
        problems.append("no check was made")
    return {"schema": RESULT_SCHEMA, "program": SN.PROGRAM_ID, "test": test, "job": job,
            "result": "FAIL" if problems else "PASS", "checks": dict(sorted(checks.items())),
            "problems": problems, "measurements": measurements or {}, **run_env(), "created_utc": now_utc()}


# -- restore ---------------------------------------------------------------------------------------

def _has_files(d: Path | None) -> bool:
    return d is not None and d.is_dir() and not d.is_symlink() and any(d.iterdir())


def _from_dir(d: Path, address: str, dest: Path) -> tuple[dict, str, bytes]:
    """Unpack ``d``'s snapshot.tar into ``dest``, every member checked against the manifest at ``address``."""
    raw = (d / RL.MANIFEST).read_bytes()
    man = SN.load_manifest(raw, address)
    tar_sha = SN.restore(d / RL.TAR, man, dest)
    return man, tar_sha, raw


def _clear(dest: Path) -> None:
    """Remove what a failed restore left in ``dest`` (a directory the restore created or found empty)."""
    if dest.is_symlink():
        raise HarnessError(f"{dest} is a symlink")
    if dest.exists():
        shutil.rmtree(dest)


def check_assets(rel: dict, d: Path) -> dict:
    """Every release asset in ``d`` hashes to GitHub's digest for it; the first that does not is named."""
    assets = RL.asset_map(rel)
    got = {}
    for n in RL.ASSETS:
        p = d / n
        if not p.is_file() or p.is_symlink():
            raise RL.ReleaseError(f"{n}: missing from {d}")
        got[n] = "sha256:" + RL.sha256_file(p)
        if got[n] != assets[n]["digest"]:
            raise RL.ReleaseError(f"{n}: sha256 {got[n]} is not the release's digest {assets[n]['digest']}; "
                                  "the asset is not the published snapshot")
    return got


def _overlaps(a: Path, b: Path) -> bool:
    a, b = a.resolve(), b.resolve()
    return a == b or a in b.parents or b in a.parents


def _refill(src: Path, cache_dir: Path, dest: Path) -> None:
    if cache_dir.is_symlink():
        raise HarnessError(f"{cache_dir} is a symlink")
    if _overlaps(cache_dir, src) or _overlaps(cache_dir, dest):
        raise HarnessError(f"the cache directory {cache_dir} overlaps the assets or the restored tree")
    if cache_dir.exists():
        shutil.rmtree(cache_dir)
    cache_dir.mkdir(parents=True)
    for n in RL.ASSETS:
        shutil.copyfile(src / n, cache_dir / n)


def restore(address: str, dest: Path, assets_dir: Path, *, commit: str, cache_dir: Path | None = None, gh=None,
            refill_cache: bool = False, expect_source: str | None = None, manifest_out: Path | None = None) -> dict:
    """Restore the snapshot at ``address`` into ``dest``: the cache if it holds it whole, else the readiness
    commit ``commit``'s release."""
    RL.tag_for(address, commit)  # a snapshot address and a readiness commit, or refused
    SN._empty_dir(dest)  # new or empty, checked once: a restore never writes over (or clears) existing files
    if cache_dir is not None and _overlaps(cache_dir, dest):
        raise HarnessError(f"the cache directory {cache_dir} overlaps the restore destination {dest}")
    rec: dict = {"schema": RECEIPT_SCHEMA, "address": address, "commit": commit, "source": None,
                 "fallback_reason": None, "seconds": {}}
    man = tar_sha = raw = None
    if cache_dir is not None:
        t = time.monotonic()
        if not _has_files(cache_dir):
            rec["fallback_reason"] = f"{CACHE_MISS}: no cached snapshot in {cache_dir}"
        else:
            try:
                man, tar_sha, raw = _from_dir(cache_dir, address, dest)
                rec["source"] = CACHE
            except (SN.SnapshotError, OSError, ValueError) as exc:
                rec["fallback_reason"] = f"{CACHE_INVALID}: {type(exc).__name__}: {exc}"[:400]
                _clear(dest)
        rec["seconds"]["cache"] = round(time.monotonic() - t, 1)
    if rec["source"] is None:
        if gh is None:
            raise HarnessError("the cache cannot restore the snapshot and no release was given")
        t = time.monotonic()
        rel = RL.the_snapshot(gh, commit, address)
        if not _has_files(assets_dir):
            RL.download(gh, assets_dir, commit, address)  # each asset checked against GitHub's digest
        rec["seconds"]["download"] = round(time.monotonic() - t, 1)
        t = time.monotonic()
        rec["asset_digests"] = check_assets(rel, assets_dir)  # again, right before use
        man, tar_sha, raw = _from_dir(assets_dir, address, dest)
        rec["source"] = RELEASE
        rec["release"] = RL.summary(rel)
        rec["seconds"]["unpack"] = round(time.monotonic() - t, 1)
        if refill_cache and cache_dir is not None:
            _refill(assets_dir, cache_dir, dest)
            rec["cache_refilled"] = str(cache_dir)
    t = time.monotonic()
    problems = SN.verify_tree(dest, man)
    if problems:
        raise SN.SnapshotError(f"{len(problems)} restored file(s) differ from the manifest; first: {problems[0]}")
    rec.update({"tar_sha256": tar_sha, "files": man["counts"]["files"], "counts": man["counts"],
                "tree_digest": SN.tree_digest(dest)})
    rec["seconds"]["verify"] = round(time.monotonic() - t, 1)
    if manifest_out is not None:
        manifest_out.parent.mkdir(parents=True, exist_ok=True)
        manifest_out.write_bytes(raw)
    if expect_source is not None and rec["source"] != expect_source:
        raise HarnessError(f"the snapshot came from the {rec['source']}, not the {expect_source} "
                           f"({rec['fallback_reason']})")
    return rec


def verify(address: str, manifest: Path, dest: Path) -> dict:
    """The check right before a science phase: the restored tree is exactly the manifest's files."""
    man = SN.load_manifest(manifest.read_bytes(), address)
    t = time.monotonic()
    problems = SN.verify_tree(dest, man)
    return {"address": address, "files": man["counts"]["files"], "problems": problems[:200],
            "problem_count": len(problems), "seconds": round(time.monotonic() - t, 1)}


# -- science, network removed ----------------------------------------------------------------------

def _offline(cache: Path):
    """The listing replay and the in-process socket guard, after proving the namespace has no network."""
    net = OFF.probe()
    if not net["network_removed"]:
        raise HarnessError(f"the network is not removed: reached {net['reached']}")
    listing = L.load((cache / SN.LISTING_REL).read_bytes())
    return net, listing


def science_d0(repo: Path, cache: Path) -> dict:
    """RT-4: Dataset V3 rebuilt offline from the snapshot and compared with the committed lock byte for byte."""
    t0 = time.monotonic()
    net, listing = _offline(cache)
    sockets: list[str] = []
    error, files, opener = None, {}, None
    try:
        with OFF.guard(sockets), L.replay(listing) as opener:
            files = D.build(cache, A.DEFAULT_BASE, repo)
    except (L.ReplayRefused, OFF.NetworkRemoved, A.ArchiveError, SystemExit) as exc:
        error = f"{type(exc).__name__}: {exc}"[:400]
    refused = list(opener.refused) if opener else []
    served = len(opener.served) if opener else 0
    bad = [rel for rel, body in files.items() if not (repo / rel).is_file() or (repo / rel).read_bytes() != body]
    checks = {"network_removed": net["network_removed"] is True, "rebuilt": error is None and bool(files),
              "lock_byte_identical": bool(files) and not bad, "no_refused_request": not refused,
              "no_socket_call": not sockets}
    return {"checks": checks, "error": error, "not_identical": bad, "refused": refused[:20], "sockets": sockets[:20],
            "listing_pages_served": served, "files_compared": len(files),
            "lock_sha256": hashlib.sha256((repo / D.LOCK_REL).read_bytes()).hexdigest(),
            "seconds": round(time.monotonic() - t0, 1)}


def science_engine(repo: Path, cache: Path, work: Path, family: str = ENGINE_FAMILY) -> dict:
    """RT-11: run_node.real_market's DATA_TRUTH check for ``family`` (A2, the largest), offline."""
    from auth2 import market_io as MI
    from auth2 import run_node as RN

    t0 = time.monotonic()
    net, listing = _offline(cache)
    want = MI.family_symbols(family, MI.tables(repo))
    sockets: list[str] = []
    error, truth, opener = None, {}, None
    try:
        with OFF.guard(sockets), L.replay(listing) as opener:
            _m, _prices, _bars, truth = RN.real_market(family, repo, cache, work)
    except (L.ReplayRefused, OFF.NetworkRemoved, A.ArchiveError, SystemExit) as exc:
        error = f"{type(exc).__name__}: {exc}"[:400]
    refused = list(opener.refused) if opener else []
    written = truth.get("content_sha256_4h") or {}
    funding = sorted(p.name for p in work.glob("engine_data/*-funding.csv")) if work.is_dir() else []
    checks = {"network_removed": net["network_removed"] is True, "data_truth_pass": truth.get("status") == "PASS",
              "every_family_symbol_checked": sorted(written) == sorted(want),
              "funding_checked": funding == sorted(f"{s}-funding.csv" for s in D.A3_ASSETS),
              "no_refused_request": not refused, "no_socket_call": not sockets}
    return {"checks": checks, "error": error, "family": family, "symbols": len(want),
            "symbols_checked": len(written), "funding_files": funding, "truth_status": truth.get("status"),
            "truth_reason": truth.get("reason"), "refused": refused[:20], "sockets": sockets[:20],
            "lock_sha256": truth.get("lock_sha256"), "seconds": round(time.monotonic() - t0, 1)}


# -- RT-6: what a corrupt snapshot looks like --------------------------------------------------------

def corrupt(address: str, manifest: Path, dest: Path) -> dict:
    """Flip one byte in the middle of the first restored kline archive; the check before science must stop."""
    man = SN.load_manifest(manifest.read_bytes(), address)
    f = next(x for x in man["files"] if SN.data_kind(x["path"]) == "kline")
    p = dest / f["path"]
    data = bytearray(p.read_bytes())
    at = len(data) // 2
    data[at] ^= 0x01
    p.write_bytes(bytes(data))
    return {"file": f["path"], "offset": at, "manifest_sha256": f["sha256"],
            "now_sha256": hashlib.sha256(bytes(data)).hexdigest()}


def tamper(assets_dir: Path) -> dict:
    """Flip one byte in the middle of the downloaded snapshot.tar: an asset with the wrong digest."""
    p = assets_dir / RL.TAR
    before = RL.sha256_file(p)
    with open(p, "r+b") as f:
        f.seek(0, os.SEEK_END)
        at = f.tell() // 2
        f.seek(at)
        b = f.read(1)
        f.seek(at)
        f.write(bytes([b[0] ^ 0x01]))
    return {"file": RL.TAR, "offset": at, "sha256_before": before, "sha256_after": RL.sha256_file(p)}


# -- classifiers (RT-6, RT-7, RT-10): the jobs API, as the guard reads it ---------------------------------

def _paged(gh, path: str, key: str | None) -> list:
    out, page = [], 1
    while True:
        status, body = gh.api("GET", f"{path}{'&' if '?' in path else '?'}per_page=100&page={page}")
        if status != 200:
            raise HarnessError(f"GET {path} failed (HTTP {status}): {str(body)[:200]}")
        batch = body.get(key) if key else body
        if not isinstance(batch, list):
            raise HarnessError(f"GET {path}: no {key or 'list'} in the response")
        out += batch
        if len(batch) < 100:
            return out
        page += 1


def run_jobs(gh, run_id: int, attempt: int = 1) -> list[dict]:
    return _paged(gh, f"/repos/{gh.slug}/actions/runs/{run_id}/attempts/{attempt}/jobs", "jobs")


def annotations(gh, job_id: int) -> list[str]:
    return [str(a.get("message") or "") for a in _paged(gh, f"/repos/{gh.slug}/check-runs/{job_id}/annotations", None)
            if isinstance(a, dict)]


def _job(jobs: list[dict], name: str) -> dict | None:
    mine = [j for j in jobs if j.get("name") == name]
    return mine[0] if len(mine) == 1 else None


def _failed_step(job: dict) -> str | None:
    bad = [s.get("name") for s in job.get("steps") or [] if s.get("conclusion") == "failure"]
    return bad[0] if len(bad) == 1 else None


def classify_rt6(jobs: list[dict], notes: dict[str, list[str]], expect: dict) -> tuple[dict, dict]:
    """The corrupted file and the wrong-digest asset both stop the job before its science step, which the
    classifier reads as INFRA, and the refusal names the file."""
    checks, seen = {}, {}
    for key, name, step, needle in (("corrupt", "RT-6 corrupted restored file", VERIFY_STEP, expect.get("file")),
                                    ("digest", "RT-6 asset with the wrong digest", RESTORE_STEP, RL.TAR)):
        j = _job(jobs, name)
        c = AT.classify_job(j) if j else {"class": None, "why": f"no single job named {name!r}"}
        failed = _failed_step(j) if j else None
        named = bool(needle) and any(needle in m for m in notes.get(name, []))
        seen[key] = {"class": c["class"], "why": c["why"], "conclusion": (j or {}).get("conclusion"),
                     "failed_step": failed, "names_the_file": named, "file": needle}
        checks[f"{key}_is_infra"] = c["class"] == AT.INFRA
        checks[f"{key}_stopped_at_{'verify' if key == 'corrupt' else 'restore'}"] = failed == step
        checks[f"{key}_names_the_file"] = named
    return checks, seen


def classify_rt7(jobs: list[dict]) -> tuple[dict, dict]:
    """One probe fails in its infrastructure phase (INFRA), the other after its science step starts (SCIENCE)."""
    checks, seen = {}, {}
    for key, name, want in (("infra", "RT-7 probe infra", AT.INFRA), ("science", "RT-7 probe science", AT.SCIENCE)):
        j = _job(jobs, name)
        c = AT.classify_job(j) if j else {"class": None, "why": f"no single job named {name!r}"}
        seen[key] = {"class": c["class"], "why": c["why"], "conclusion": (j or {}).get("conclusion"),
                     "failed_step": _failed_step(j) if j else None}
        checks[f"probe_{key}_classified_{want}"] = c["class"] == want
    checks["probe_infra_failed_in_infrastructure"] = seen["infra"]["failed_step"] == INFRA_STEP
    checks["probe_science_failed_in_science"] = seen["science"]["failed_step"] == AT.SCIENCE_STEP
    return checks, seen


def classify_rt10(jobs: list[dict]) -> tuple[dict, dict]:
    """A job that runs into its 2-minute timeout bills 3 minutes: timeout + 1, never more."""
    j = _job(jobs, "RT-10 probe")
    t = PL.RT10_TIMEOUT
    if j is None:
        return {"probe_found": False}, {}
    a, b = AT._ts(j.get("started_at")), AT._ts(j.get("completed_at"))
    seconds = (b - a).total_seconds() if a and b else None
    billed = AT.billed_minutes(j, t)
    checks = {"probe_found": True, "ran_into_its_timeout": j.get("conclusion") == "cancelled",
              "ran_past_the_timeout": seconds is not None and seconds > 60 * t,
              "billed_timeout_plus_one": billed == t + 1}
    return checks, {"timeout_minutes": t, "seconds": seconds, "billed_minutes": billed,
                    "conclusion": j.get("conclusion"), "started_at": j.get("started_at"),
                    "completed_at": j.get("completed_at")}


def settled_jobs(gh, run_id: int, names: list[str], *, sleep=time.sleep) -> list[dict]:
    """The run's jobs once every job in ``names`` reads as completed: the API can trail a job's end by a
    moment. After SETTLE_TRIES reads it returns what the API says, and the classifier fails closed on any job
    that is not finished."""
    for i in range(SETTLE_TRIES):
        jobs = run_jobs(gh, run_id, 1)
        if all((j := _job(jobs, n)) is not None and j.get("status") == "completed" for n in names):
            break
        if i + 1 < SETTLE_TRIES:
            sleep(SETTLE_SECONDS)
    return jobs


def classify(test: str, gh, run_id: int, expect: dict | None = None, *, sleep=time.sleep) -> dict:
    if test not in ("RT-6", "RT-7", "RT-10"):
        raise HarnessError(f"{test} has no classifier")
    probes = [n for n in PL.TESTS[test][1] if not n.endswith(" classify")]
    jobs = settled_jobs(gh, run_id, probes, sleep=sleep)
    if test == "RT-6":
        for i in range(SETTLE_TRIES):
            notes = {name: annotations(gh, j["id"]) for name in probes if (j := _job(jobs, name))}
            if all(notes.get(n) for n in probes) or i + 1 == SETTLE_TRIES:
                break
            sleep(SETTLE_SECONDS)
        checks, seen = classify_rt6(jobs, notes, expect or {})
    elif test == "RT-7":
        checks, seen = classify_rt7(jobs)
    else:
        checks, seen = classify_rt10(jobs)
    return result(test, f"{test} classify", checks, {"jobs": seen, "run_id": run_id})


# -- verdicts ----------------------------------------------------------------------------------------

def lock_counts(repo: Path) -> dict:
    return json.loads((repo / D.LOCK_REL).read_text())["counts"]


def _prep_checks(rec: dict, repo: Path) -> dict:
    lock = lock_counts(repo)
    counts = rec.get("counts") or {}
    return {"no_checksum_failure": rec.get("checksum_failures") == 0,
            "listing_replays_the_archive": rec.get("replay_equivalent") is True,
            "kline_files_are_the_locks": counts.get("kline_archive_files") == lock["kline_archive_files"],
            "funding_files_are_the_locks": counts.get("funding_archive_files") == lock["funding_archive_files"],
            "bound_to_the_committed_lock": rec.get("lock_sha256") ==
            hashlib.sha256((repo / D.LOCK_REL).read_bytes()).hexdigest(),
            "duration_recorded": isinstance(rec.get("seconds"), dict) and "fetch" in rec["seconds"],
            "thirty_two_workers": rec.get("workers") == 32}


def _tag(address, commit) -> str | None:
    try:
        return RL.tag_for(address, commit)
    except RL.ReleaseError:
        return None


SNAPSHOT_BINDING = ("address", "commit", "tag", "release_id")   # which release a verdict read, by its identity


def snapshot_binding(rel) -> dict | None:
    """The identity of the release a test read (a release summary), carried in its verdict for the record."""
    return {k: rel.get(k) for k in SNAPSHOT_BINDING} if isinstance(rel, dict) else None


def bound_to(rel, commit) -> bool:
    """The release summary ``rel`` is the snapshot release of the readiness commit ``commit``."""
    b = snapshot_binding(rel)
    return b is not None and RL.is_commit(commit) and b["commit"] == commit \
        and b["tag"] == _tag(b["address"], commit) and isinstance(b["release_id"], int) \
        and not isinstance(b["release_id"], bool)


def _this_run(rec: dict, env: dict, commit) -> bool:
    """The preparation record is this run's own, made at this run's commit: fresh, current-run evidence."""
    return RL.is_commit(commit) and env.get("sha") == commit and rec.get("commit") == commit \
        and env.get("run_id") is not None and str(rec.get("run_id")) == str(env["run_id"]) \
        and str(rec.get("run_attempt")) == "1"


def compare_release(directory: Path, repo: Path, gh, commit: str) -> dict:
    """RT-2: a second cold preparation at the readiness commit ``commit``, not published, is that commit's
    published snapshot byte for byte."""
    rec = read_json(directory / RL.RECORD)
    raw = (directory / RL.MANIFEST).read_bytes()
    tar_sha = RL.sha256_file(directory / RL.TAR)
    rel = RL.the_snapshot(gh, commit)
    assets = RL.asset_map(rel)
    env = run_env()
    checks = _prep_checks(rec, repo)
    checks.update({"same_manifest_digest": SN.address(raw) == RL.address_of(rel["tag_name"]) == rec.get("address"),
                   "same_tar_sha256": f"sha256:{tar_sha}" == assets[RL.TAR]["digest"]
                   and tar_sha == rec.get("tar_sha256"),
                   "prepared_cold_by_this_run_at_this_commit": _this_run(rec, env, commit),
                   "release_bound_to_this_commit": bound_to(RL.summary(rel), commit) and env.get("sha") == commit})
    return result("RT-2", "Cold preparation", checks,
                  {"address": SN.address(raw), "tar_sha256": tar_sha, "commit": commit, "release": RL.summary(rel),
                   "snapshot_release": snapshot_binding(RL.summary(rel)),
                   "preparation": {k: rec.get(k) for k in ("seconds", "tar_bytes", "counts", "workers", "symbols",
                                                           "symbols_with_lock_identity", "run_id")}})


def verdict(test: str, job: str, inputs: list[Path], repo: Path) -> dict:
    """A test's result record from the files its job wrote."""
    docs = [read_json(p) for p in inputs]
    if test == "RT-1":
        rec, pub = docs
        env = run_env()
        commit, mode, by = env["sha"], pub.get("result"), pub.get("published_by_run")
        assets = pub.get("assets") or {}
        checks = _prep_checks(rec, repo)
        checks.update({
            "published_or_verified": mode in (RL.PUBLISHED, RL.VERIFIED_EXISTING),
            "immutable": pub.get("immutable") is True,
            "prepared_cold_by_this_run_at_this_commit": _this_run(rec, env, commit),
            "release_bound_to_this_commit": RL.is_commit(commit) and pub.get("commit") == commit
            and pub.get("tag") == _tag(rec.get("address"), commit),
            "tag_at_this_commit": RL.is_commit(commit) and pub.get("tag_commit") == commit,
            "release_is_this_preparation": pub.get("address") == rec.get("address")
            and (assets.get(RL.MANIFEST) or {}).get("digest") == rec.get("address")
            and (assets.get(RL.TAR) or {}).get("digest") == f"sha256:{rec.get('tar_sha256')}",
            "published_by_an_rt1_run_at_this_commit": isinstance(by, int) and not isinstance(by, bool)
            and env["run_id"] is not None and ((mode == RL.PUBLISHED and str(by) == str(env["run_id"]))
                                               or (mode == RL.VERIFIED_EXISTING and str(by) != str(env["run_id"])))})
        meas = {"address": rec.get("address"), "tar_sha256": rec.get("tar_sha256"), "tar_bytes": rec.get("tar_bytes"),
                "commit": commit, "publication": mode, "published_by_run": by,
                "counts": rec.get("counts"), "seconds": rec.get("seconds"), "release": {
                    k: pub.get(k) for k in ("tag", "commit", "release_id", "published_at", "assets", "tag_commit")}}
        return result(test, job, checks, meas)
    if test == "RT-3":
        (probe,) = docs
        probes = probe.get("probes") or {}
        checks = {"probe_passed": probe.get("result") == "PASS", "probes_made": len(probes) >= 4,
                  "every_write_refused": bool(probes) and all(v.get("refused") is True for v in probes.values()),
                  "probed_this_commits_release": bound_to(probe.get("release"), run_env()["sha"])}
        if probe.get("part") == "immutability":
            checks["release_unchanged"] = probe.get("release_unchanged") is True
        return result(test, job, checks, {"part": probe.get("part"), "probes": probes,
                                          "snapshot_release": snapshot_binding(probe.get("release"))})
    if test in ("RT-4", "RT-11"):
        receipt, sci = docs
        sha = run_env()["sha"]
        checks = {"restored_from_the_release": receipt.get("source") == RELEASE, **sci.get("checks", {}),
                  "restored_this_commits_release": receipt.get("commit") == sha and bound_to(receipt.get("release"), sha)}
        if test == "RT-4":
            checks["no_cache_used"] = receipt.get("fallback_reason") is None and \
                "cache" not in (receipt.get("seconds") or {})
        meas = {"restore": {k: receipt.get(k) for k in ("seconds", "files", "tree_digest", "tar_sha256")},
                "science": {k: v for k, v in sci.items() if k != "checks"},
                "snapshot_release": snapshot_binding(receipt.get("release"))}
        return result(test, job, checks, meas)
    if test == "RT-5":
        cold, warm = docs
        checks = {"cold_fell_back_to_the_release": cold.get("source") == RELEASE
                  and str(cold.get("fallback_reason")).startswith(CACHE_MISS),
                  "warm_restored_from_the_cache": warm.get("source") == CACHE and warm.get("fallback_reason") is None,
                  "same_snapshot": cold.get("address") == warm.get("address") is not None,
                  "same_tree_digest": cold.get("tree_digest") == warm.get("tree_digest") is not None,
                  "every_file_verified": cold.get("files") == warm.get("files") and bool(cold.get("files")),
                  "cold_restored_this_commits_release": cold.get("commit") == warm.get("commit") == run_env()["sha"]
                  and bound_to(cold.get("release"), run_env()["sha"])}
        return result(test, job, checks, {"cold": {k: cold.get(k) for k in ("seconds", "fallback_reason", "files")},
                                          "warm": {k: warm.get(k) for k in ("seconds", "files")},
                                          "tree_digest": warm.get("tree_digest"),
                                          "snapshot_release": snapshot_binding(cold.get("release"))})
    raise HarnessError(f"{test} has no verdict here")


# -- CLI ---------------------------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("restore")
    r.add_argument("--address", required=True)
    r.add_argument("--commit", required=True, help="the readiness commit (the run's GITHUB_SHA)")
    r.add_argument("--dest", required=True)
    r.add_argument("--assets-dir", required=True)
    r.add_argument("--cache-dir")
    r.add_argument("--refill-cache", action="store_true")
    r.add_argument("--expect-source", choices=(CACHE, RELEASE))
    r.add_argument("--manifest-out")
    r.add_argument("--repo-slug", required=True)
    r.add_argument("--out", required=True)
    v = sub.add_parser("verify")
    for name in ("--address", "--manifest", "--dest", "--out"):
        v.add_argument(name, required=True)
    for name in ("d0", "engine"):
        s = sub.add_parser(name)
        s.add_argument("--repo", default=".")
        s.add_argument("--cache", required=True)
        s.add_argument("--out", required=True)
        if name == "engine":
            s.add_argument("--work", required=True)
    c = sub.add_parser("corrupt")
    for name in ("--address", "--manifest", "--dest", "--out"):
        c.add_argument(name, required=True)
    t = sub.add_parser("tamper")
    t.add_argument("--assets-dir", required=True)
    t.add_argument("--out", required=True)
    k = sub.add_parser("classify")
    k.add_argument("--test", required=True, choices=("RT-6", "RT-7", "RT-10"))
    k.add_argument("--repo-slug", required=True)
    k.add_argument("--run-id", type=int, required=True)
    k.add_argument("--expect")
    k.add_argument("--out", required=True)
    q = sub.add_parser("prep-check")
    q.add_argument("--record", required=True)
    q.add_argument("--repo", default=".")
    m = sub.add_parser("compare-release")
    m.add_argument("--dir", required=True)
    m.add_argument("--commit", required=True, help="the readiness commit (the run's GITHUB_SHA)")
    m.add_argument("--repo", default=".")
    m.add_argument("--repo-slug", required=True)
    m.add_argument("--out", required=True)
    d = sub.add_parser("verdict")
    d.add_argument("--test", required=True, choices=("RT-1", "RT-3", "RT-4", "RT-5", "RT-11"))
    d.add_argument("--job", required=True)
    d.add_argument("--repo", default=".")
    d.add_argument("--out", required=True)
    d.add_argument("inputs", nargs="+")
    f = sub.add_parser("fail")
    f.add_argument("--test", required=True, choices=PL.RUN_TESTS)
    f.add_argument("--job", required=True)
    f.add_argument("--reason", required=True)
    f.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    if a.cmd == "prep-check":  # RT-1 publishes an immutable release once: its preparation checks come first
        checks = _prep_checks(read_json(Path(a.record)), Path(a.repo).resolve())
        bad = sorted(k for k, v in checks.items() if v is not True)
        for k in bad:
            print(f"::error::PREPARATION_CHECK: {k} does not hold; nothing is published")
        print(f"PREPARATION_CHECK = {'FAIL' if bad else 'PASS'} ({len(checks) - len(bad)}/{len(checks)})")
        return 3 if bad else 0
    out = Path(a.out)
    if a.cmd == "fail":  # a verdict job whose test could not finish publishes that, not nothing
        write_json(out, result(a.test, a.job, {}, problems=[a.reason[:600]]))
        print(f"{a.test} = FAIL: {a.reason[:600]}")
        return 3
    ok_word = "PASS"
    try:
        if a.cmd == "restore":
            rec = restore(a.address, Path(a.dest), Path(a.assets_dir), commit=a.commit,
                          cache_dir=Path(a.cache_dir) if a.cache_dir else None, gh=RL.GH(a.repo_slug),
                          refill_cache=a.refill_cache, expect_source=a.expect_source,
                          manifest_out=Path(a.manifest_out) if a.manifest_out else None)
            write_json(out, rec)
            print(f"SNAPSHOT_RESTORE = PASS ({rec['files']} files from the {rec['source']}"
                  f"{'; ' + rec['fallback_reason'] if rec['fallback_reason'] else ''})")
            return 0
        if a.cmd == "verify":
            rec = verify(a.address, Path(a.manifest), Path(a.dest))
            write_json(out, rec)
            for line in rec["problems"][:40]:
                print(f"::error::SNAPSHOT_VERIFY: {line}")
            if rec["problem_count"]:
                print(f"SNAPSHOT_VERIFY = FAIL ({rec['problem_count']} file(s) differ; the science phase must not "
                      "start)")
                return 3
            print(f"SNAPSHOT_VERIFY = PASS ({rec['files']} files)")
            return 0
        if a.cmd in ("d0", "engine"):
            if a.cmd == "d0":
                rec = science_d0(Path(a.repo).resolve(), Path(a.cache).resolve())
            else:
                rec = science_engine(Path(a.repo).resolve(), Path(a.cache).resolve(), Path(a.work).resolve())
            write_json(out, rec)
            bad = sorted(k for k, v in rec["checks"].items() if v is not True)
            if bad or rec.get("error"):
                print(f"::error::SCIENCE_{a.cmd.upper()} = FAIL: {bad} {rec.get('error') or ''}"[:1500])
                return 3
            print(f"SCIENCE_{a.cmd.upper()} = PASS ({rec['seconds']} s)")
            return 0
        if a.cmd == "corrupt":
            write_json(out, corrupt(a.address, Path(a.manifest), Path(a.dest)))
            print(f"corrupted {read_json(out)['file']} (RT-6)")
            return 0
        if a.cmd == "tamper":
            write_json(out, tamper(Path(a.assets_dir)))
            print(f"tampered {RL.TAR} (RT-6)")
            return 0
        if a.cmd == "classify":
            rec = classify(a.test, RL.GH(a.repo_slug), a.run_id, read_json(Path(a.expect)) if a.expect else None)
        elif a.cmd == "compare-release":
            rec = compare_release(Path(a.dir), Path(a.repo).resolve(), RL.GH(a.repo_slug), a.commit)
        else:
            rec = verdict(a.test, a.job, [Path(p) for p in a.inputs], Path(a.repo).resolve())
        write_json(out, rec)
        ok_word = rec["result"]
        print(f"{rec['test']} = {ok_word}" + (f": {rec['problems'][:5]}" if rec["problems"] else ""))
        return 0 if ok_word == "PASS" else 3
    except (HarnessError, RL.ReleaseError, SN.SnapshotError, OSError, ValueError, KeyError) as exc:
        print(f"::error::{a.cmd.upper()}_REFUSED: {str(exc)[:1500]}")
        if a.cmd in ("classify", "compare-release", "verdict"):
            write_json(out, result(getattr(a, "test", None) or "RT-2", getattr(a, "job", None) or a.cmd, {},
                                   problems=[f"{type(exc).__name__}: {str(exc)[:600]}"]))
        print(f"{a.cmd.upper()} = FAIL")
        return 3


if __name__ == "__main__":
    sys.exit(main())
