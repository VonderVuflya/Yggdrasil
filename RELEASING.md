# Releasing Yggdrasil

Yggdrasil ships through several channels so users install with whatever they
already use. **They all install the same Python package — PyPI is the source of
truth; npm and Homebrew bootstrap or wrap it.** Publish in this order.

Version lives in two places — keep them in sync before a release:
`yggdrasil/__init__.py` (`__version__`), `pyproject.toml` (`version`), and
`clients/npm/package.json` (`version`). Tag `vX.Y.Z` after pushing.

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
