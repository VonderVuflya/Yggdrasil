# Releasing Yggdrasil

Yggdrasil ships through several channels so users install with whatever they
already use. **They all install the same Python package — PyPI is the source of
truth; npm and Homebrew bootstrap or wrap it.** Publish in this order.

**Use `bash scripts/release.sh <version>`** — it bumps every file, checks the
CHANGELOG, runs the tests, and publishes each channel in order. Run it **from
`main`**: step 5 pushes `HEAD:$BRANCH`, so from a feature branch it tags and
publishes that branch instead. `--dry-run` prints the plan without touching
anything.

---

## Writing the release notes

A CHANGELOG reader is deciding one thing: **do I upgrade, and does anything
change for me?** They are not reviewing the fix. The mechanism belongs in the
commit — git is right there for anyone who wants it, and duplicating it here is
what turned single releases into 60-line essays nobody reads.

- **One line per change.** Two only if there's a real caveat.
- **Say what the user sees**, not how it works. "Arrow keys no longer quit the
  wizard", not "sys.stdin is a TextIOWrapper, so read(1) buffers…".
- **Say what to do**, when there's something to do — reinstall, re-run `ygg
  redeploy`, rotate a key. This is the part long notes forget: it's possible to
  explain a bug in seven lines and never tell anyone how to get the fix.
- **Name the blast radius** for anything breaking, and nothing else.
- **A themed title** (`## [0.12.0] — date — bring your own engine`) is for
  releases with a story. Patches just get the version and date.

Rule of thumb: a patch is 2–5 lines, a minor is under 15. If it's longer, it's
a commit message that wandered into the wrong file.

Write new sections under `## [Unreleased]` and let `release.sh` date them —
**dating a section is not the same as shipping it**. Twice now, notes were
written into a version's section before that version went out, so the published
release claimed changes it didn't contain.

The version lives in **ten** files, not the three this page used to list:

```
yggdrasil/__init__.py            pyproject.toml           clients/npm/package.json
server.json                      packaging/mcpb/manifest.json
.claude-plugin/plugin.json       .claude-plugin/marketplace.json
.codex-plugin/plugin.json        .cursor-plugin/plugin.json
.cursor-plugin/marketplace.json
```

`release.sh` bumps all ten. Only bump by hand if you're not using it — and then
check them all, because a stale plugin manifest ships a wrong version to the
marketplace without failing anything. `packaging/homebrew/yggdrasil.rb` is the
exception: it needs the sdist's sha256, so it's patched *after* PyPI publishes.

Tag `vX.Y.Z` after pushing (release.sh does this too).

---

## 1. PyPI — `yggdrasil-memory` (do this first)

Gives `uvx`, `pipx`, and `pip`. Needs a [PyPI account](https://pypi.org/account/register/)
and an API token.

```bash
# build sdist + wheel into dist/
rm -rf dist && uv build            # or: python3 -m build

# (optional) dry-run on TestPyPI:
#   uv publish --publish-url https://test.pypi.org/legacy/ --token <testpypi-token>

# publish to PyPI:
uv publish --token pypi-XXXXXXXX   # or: twine upload dist/*

# verify (fresh, no clone):
uvx --from yggdrasil-memory ygg version
```

After this, `uvx --from yggdrasil-memory ygg install`, `pipx install yggdrasil-memory`,
and `pip install yggdrasil-memory` all work.

---

## 2. npm — `yggdrasil-memory` launcher

Gives `npx yggdrasil-memory ...` and `npm i -g yggdrasil-memory` (→ `ygg`).
The package is a thin launcher (`clients/npm/bin/ygg.js`) that runs the PyPI
package via `uv`/`pipx`. Needs an [npm account](https://www.npmjs.com/signup) and
`npm login`.

```bash
cd clients/npm
cp ../../LICENSE ./LICENSE          # bundle the license into the npm tarball
npm publish --access public

# verify:
npx yggdrasil-memory version
```

> If the bare name `yggdrasil-memory` is taken on npm, publish under a scope
> (`@vondervuflya/yggdrasil`): set `"name"` in `clients/npm/package.json`, then
> `npm publish --access public`. Update the README install matrix accordingly.

---

## 3. Homebrew — `VonderVuflya/tap/yggdrasil`

Gives `brew install VonderVuflya/tap/yggdrasil` on macOS/Linux. Needs a public
GitHub repo named **`homebrew-tap`** under your account. Do this *after* PyPI
(the formula points at the PyPI sdist).

```bash
# a) create the tap repo (once):
gh repo create VonderVuflya/homebrew-tap --public -d "Homebrew tap for Yggdrasil"

# b) get the exact sdist URL + sha256 from PyPI:
curl -s https://pypi.org/pypi/yggdrasil-memory/json | python3 -c '
import sys, json
d = json.load(sys.stdin)
s = [f for f in d["releases"]["0.1.0"] if f["packagetype"] == "sdist"][0]
print("url:   ", s["url"])
print("sha256:", s["digests"]["sha256"])'

# c) copy packaging/homebrew/yggdrasil.rb -> the tap as Formula/yggdrasil.rb,
#    replace `url` + `sha256` with the values above, commit and push.

# verify:
brew install VonderVuflya/tap/yggdrasil
ygg version
```

To bump later: update `url`/`sha256` (and `version`) in the formula and push.

---

## 4. (optional) Official MCP Registry

Once on PyPI, register the metadata so MCP clients can discover it:

```bash
brew install mcp-publisher        # or download the binary
mcp-publisher init                # generates server.json (registryType: pypi)
mcp-publisher login               # GitHub OAuth
mcp-publisher publish
```

---

## Channel summary

| Channel | Command | Wraps |
| --- | --- | --- |
| uv | `uvx --from yggdrasil-memory ygg install` | PyPI (native) |
| pipx | `pipx install yggdrasil-memory && ygg install` | PyPI (native) |
| pip | `pip install yggdrasil-memory && ygg install` | PyPI (native) |
| npm / npx | `npx yggdrasil-memory install` | launcher → uv → PyPI |
| Homebrew | `brew install VonderVuflya/tap/yggdrasil` | venv from PyPI sdist |
| from source | `uvx --from git+https://github.com/VonderVuflya/yggdrasil.git ygg install` | this repo (no registry) |
