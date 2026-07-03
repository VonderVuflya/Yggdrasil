# Release plan — 0.5.5 → 0.6.0 → 0.7.0

Prepared 2026-07-03. **Nothing here is pushed or published yet** — this is the
turnkey sequence to roll out the three staged releases when you're ready.

## What's prepared

Three annotated tags, each a **real, coherent snapshot** of progress (honest
incremental — no jump from 0.5.4 straight to 0.7.0):

| Tag | Boundary commit | Content | Version stamped in all 11 manifests |
| --- | --- | --- | --- |
| `v0.5.5` | after P0 (`3fb0086`) | audit release — security & correctness | 0.5.5 |
| `v0.6.0` | after P1 (`a090651`) | robustness, DX & CI | 0.6.0 |
| `v0.7.0` | `main` HEAD | performance, benchmark honesty, native-memory bridge | 0.7.0 |
| `v0.7.1` | `main` HEAD | seeding hardening (any endpoint · language · robustness · readable output) | 0.7.1 |

Each tag's `CHANGELOG.md` only documents up to its own version, and its version
string is consistent across `pyproject.toml`, `__init__.py`, `server.json`,
`clients/npm/package.json`, `packaging/mcpb/manifest.json`, and the 5 plugin
manifests. Verified.

**DAG note:** `v0.5.5` and `v0.6.0` are commits that branch off their boundary
commit (they are not ancestors of `main`), because each carries only its own
version bump + changelog. `main` ends at `Release 0.7.1` (`v0.7.1`); `v0.7.0` is one release commit back. When you
push tags, GitHub will show the two intermediate tags as points off the main
line — normal for backfilled releases; PyPI/GitHub Releases build fine from any
tag.

Rollback if needed: `git branch backup-pre-release-prep` still points at the
pre-prep HEAD (`306e0ae`); delete the tags + reset `main` to it to undo.

## Prerequisites (one-time)

`scripts/release.sh` loads credentials from `~/.yggdrasil/release.env`. Put your
tokens there once so you never re-enter them:

```bash
mkdir -p ~/.yggdrasil
cat >> ~/.yggdrasil/release.env <<'ENV'
export UV_PUBLISH_TOKEN=pypi-...        # PyPI
# npm: `npm login` once; gh: `gh auth login`; mcp: `mcp-publisher login`
ENV
```

You also need a GitHub remote and `gh auth` for Releases, and (optional)
`YGG_TAP_DIR=/path/to/homebrew-tap` to auto-push the Homebrew formula.

## Publish sequence (run when ready)

**1. Push the branch + all three tags first** (so GitHub Releases can attach to them):

```bash
git push origin main
git push origin v0.5.5 v0.6.0 v0.7.0 v0.7.1
```

**2. Publish each version from its tag, oldest first.** `--skip-git` because the
commits + tags already exist (don't re-commit on the detached checkout):

```bash
# 0.5.5
git checkout v0.5.5
bash scripts/release.sh 0.5.5 --skip-git --yes      # bump(no-op)+build+PyPI+npm+brew+mcp+GitHub release

# 0.6.0
git checkout v0.6.0
bash scripts/release.sh 0.6.0 --skip-git --yes

# 0.7.0
git checkout v0.7.0
bash scripts/release.sh 0.7.0 --skip-git --yes

# 0.7.1
git checkout main            # main HEAD == v0.7.1
bash scripts/release.sh 0.7.1 --skip-git --yes

git checkout main            # return to the branch
```

Dry-run any of them first with `--dry-run` (prints every step, publishes
nothing). Skip a channel with `--skip-pypi` / `--skip-npm` / `--skip-brew` /
`--skip-mcp` / `--skip-gh`. A channel whose tool/credential is missing is
skipped with a warning, and a done/skipped summary prints at the end.

**3. Verify** each version shows up: <https://pypi.org/project/yggdrasil-memory/#history>,
`npm view yggdrasil-memory versions`, and the GitHub Releases page.

## Notes

- The `.mcpb` desktop bundles are built fresh by `release.sh` (they're gitignored)
  and attached to the GitHub release — no stale binaries in git.
- If you'd rather ship a single release, just do step 2 for `v0.7.0` only; PyPI
  then goes 0.5.4 → 0.7.0 (the CHANGELOG still documents 0.5.5/0.6.0 as sections).
