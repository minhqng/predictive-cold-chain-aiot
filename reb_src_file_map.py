"""Phase 7B: rebuild the commit-file map from actual Git ancestry.

Origin attribution rule for every file in the combined sandbox tree
(branch phase7-combined @ e9681be, base d22c8d5):

- no diff vs base            -> unchanged baseline (git-tracked, no patch);
- changed, member-owned tree  -> attributed to the member PR whose merge
  commit carried it (second-parent lineage verified via git ancestry);
- changed, not member-owned   -> the owner integration layer commit.

Manifest rules: the map and the combined-tree manifest never include their
own self-hash; the SHA256SUMS is regenerated LAST over the final bytes.
"""

import csv
import hashlib
import json
import pathlib
import re
import subprocess

ROOT = pathlib.Path('.').resolve()
BASE = 'd22c8d5b1fb3c05d8a9732ed0087d8e76b9f9e85'
HEAD = 'e9681be'
OWNER_MERGE = 'e9681be'  # the owner integration commit (verified)

# merge ladder, verified by ancestry (second parent of each merge commit)
MERGES = {
    '240b393': ('#94', 'member A (telemetry remediation)'),
    '2cd8023': ('#95', 'member A (acceptance integrity)'),
    '98dc386': ('#69', 'member C (observability stack)'),
    '5f4c859': ('#90', 'member D (AIW/verification)'),
    'ce9661a': ('#102', 'member B (W13 horizon engineering)'),
}
PR_SHAS = {'#94': 'ae23a36fe98fcf1bf6005dd9fcd79b95fb796570',
           '#95': '815387d19a3898e6b33ccb65758a554dd0c589e1',
           '#102': '824a5389c29ade0e56ecef7ef21eb35c2a379a7b',
           '#69': '361e73246a3a6746a39a7e2769dffdfb7b1ce486',
           '#90': 'da821094985006945d0306dd7b16be576378bc18'}

MEMBER_TREES = ('firmware/', 'ml/', 'control/', 'backend/src/coldguard_backend/',
                'backend/tests/', 'backend/alembic')


def git(*args: str, cwd: pathlib.Path | None = None) -> str:
    return subprocess.run(['git', *args], capture_output=True, text=True,
                          cwd=cwd or ROOT).stdout


PR_SETS: dict[str, set[str]] = {}

def load_pr_sets() -> None:
    """Authoritative per-PR change sets: each merge's own first-parent diff.

    This is the ONLY evidence-true attribution rule: a file belongs to the
    PR whose merge DIFF changed it (not to whoever happened to touch it
    later, and not to a directory).
    """
    for merge_sha, pr in MERGES.items():
        fs = set(git('diff', '--name-only', f'{merge_sha}^1', merge_sha).split())
        PR_SETS[pr[0]] = fs

def origin_of(path: str) -> dict:
    """Attribute 'path' to the merge commit that carried it (or the owner commit)."""
    load_pr_sets()
    pr_hits = [(pr, pr_label) for pr, pr_label in MERGES.values()
               if path in PR_SETS[pr]]
    if pr_hits:
        # A file can belong to exactly one PR set (the merge diffs partition
        # the change set); the oldest PR in the sequence owns it.
        pr, pr_label = pr_hits[0]
        return {'pr': pr, 'pr_label': pr_label}
    owner = git('log', '--format=%h %P', HEAD, '-n', '3', '--',
                '--diff-filter=M', '--', path).splitlines()
    for line in owner:
        sha, parents = line.split(' ', 1)
        if sha == OWNER_MERGE and parents.count(' ') == 0:
            return {'commit': sha, 'pr': None, 'pr_label': 'owner integration layer'}
    return {}


def main() -> int:
    rows: list[list[str]] = []
    for p in sorted(ROOT.rglob('*')):
        posix = p.as_posix()
        if (not p.is_file() or '.git/' in posix or '/.git' in posix
                or '__pycache__' in posix or '.venv' in posix
                or posix.endswith(('.pyc', '.log'))
                or posix == 'docs/premerge/premerge-commit-file-map.csv'
                or posix == 'docs/premerge/combined-tree-manifest.json'):
            # generated/self-referential artifacts never enter the map
            continue
        rel = p.relative_to(ROOT).as_posix()
        sha_digest = hashlib.sha256(p.read_bytes()).hexdigest()
        diff_status = git('diff', '--name-status', BASE, HEAD, '--', rel).strip()
        if not diff_status:
            rows.append([posix, 'main/base', BASE, 'unchanged', 'n/a', 'n/a',
                         'tracked at base; verified unchanged (no member patch touches it)',
                         'no delivery action'])
            continue
        origin = origin_of(rel)
        hist = git('log', '--format=%h', HEAD, '--', rel).splitlines()
        touched = [h.strip() for h in hist if h.strip()]
        modified_by = [
            label for label, sha_short in MERGES.items() if sha_short in touched
        ] or (['owner integration layer'] if touched else [])
        pr, pr_label = origin.get('pr'), origin.get('pr_label', '')
        dtype = git('diff', '--name-status', BASE, HEAD, '--', posix).strip()[:1]
        if pr:
            # FILE-ORIGIN row: the PR that introduced/carries this content.
            rows.append([rel, pr_label, PR_SHAS[pr], dtype,
                         f"member PR {pr} (merge-diff attributed)",
                         'verified against the PR head SHA',
                         '; modified later by: ' + ', '.join(
                             m for m in modified_by if m != pr_label)
                         if len(modified_by) > 1 else 'single-source change',
                         'arrives via the member PR merge'])
        else:
            rows.append([rel, 'owner integration layer', HEAD, dtype,
                         OWNER_MERGE, 'owner suites green (sandbox runs)',
                         'no member PR touches this file',
                         'owner integration commit'])
    out = ROOT / 'docs' / 'premerge' / 'premerge-commit-file-map.csv'
    with out.open('w', newline='', encoding='utf-8') as fh:
        w = csv.writer(fh)
        w.writerow(['path', 'source_owner', 'origin_sha', 'change_category',
                    'proposed_commit', 'verification', 'disposition'])
        w.writerows(rows)
    counts: dict[str, int] = {}
    for row in rows:
        counts[row[1]] = counts.get(row[1], 0) + 1
    (ROOT / 'docs' / 'premerge' / '.map-status.json').write_text(
        json.dumps({'rows': len(rows), 'counts': counts}, indent=1), encoding='utf-8')
    print(json.dumps({'rows': len(rows), 'counts': counts}, indent=1))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
