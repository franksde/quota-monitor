# Releasing quota-monitor

How to cut a release across the three artifacts: **GitHub tag**, **PyPI
package**, and **Homebrew tap formula**. Written so an unfamiliar human
or AI agent can run the full pipeline cold.

If you are mid-release and something fails, stop and read **Recovery**
at the bottom before re-running anything destructive.

---

## What gets shipped

| Surface | Repo / location | What changes |
|---|---|---|
| GitHub release | `franksde/quota-monitor` | A signed-history `vX.Y.Z` annotated tag on `main` and a new GitHub Release page |
| PyPI package | `quota-monitor` on pypi.org | A `quota-monitor==X.Y.Z` wheel + sdist installable via `pip` / `uv` |
| Homebrew formula | `franksde/homebrew-tap` (the tap is `franksde/tap`) | `Formula/quota-monitor.rb` bumped to point at the new tag's source tarball |

Users install with **either** `pip install quota-monitor` **or**
`brew install franksde/tap/quota-monitor`. Both must work after a release.

---

## Prerequisites

Before your first release:

- **`gh` authenticated** as the maintainer (`gh auth status` shows
  `franksde`). Used to clone the tap repo and create the GitHub Release.
- **PyPI token** stored in `~/.pypirc` so `twine upload` is non-interactive:

  ```ini
  # ~/.pypirc
  [pypi]
    username = __token__
    password = pypi-AgEI...<your token>
  ```

  Get a project-scoped token from https://pypi.org/manage/account/token/
  (scope: `quota-monitor` only). `chmod 600 ~/.pypirc`. Never commit it,
  never paste it into a chat session, never store it in repo `.env`.
- **Build tooling** in the project venv:

  ```bash
  source .venv/bin/activate
  pip install build twine
  ```

  Both are dev-only — they intentionally are not declared in
  `[project.optional-dependencies]` to keep the runtime install fully
  stdlib.
- **Homebrew installed** locally (optional, only needed if you want to
  smoke-test the formula end to end before pushing).

---

## Pre-flight checks

Run from the repo root:

```bash
source .venv/bin/activate
python -m pytest                  # must be green; 250+ tests
git status                        # no unrelated uncommitted changes
git log origin/main..HEAD --oneline   # what you're about to ship
```

If `pytest` is red, do not proceed. If `git status` shows stray files,
either stage them deliberately or stash them.

---

## Step 1 — Bump the version

The version literal lives in three places that must stay in lockstep.
The release fails (or ships inconsistently) if you forget one.

| File | What to change |
|---|---|
| `pyproject.toml` | `version = "X.Y.Z"` |
| `quota_monitor/__init__.py` | `__version__ = "X.Y.Z"` |
| `CHANGELOG.md` | New `## vX.Y.Z — YYYY-MM-DD` section at the top |

`quota_monitor/__main__.py` reads `__version__` at runtime, and the
`User-Agent` headers in `quota_monitor/notifiers/{telegram,cloudflare_relay}.py`
do the same — no manual sync needed there.

The `CHANGELOG.md` entry should describe user-visible changes, grouped
by `feat` / `fix` / `chore`. If a release fixes something that was
observed in the wild, say so — include the date and symptom. Future
debuggers will thank you.

---

## Step 2 — Commit, tag, push

```bash
git add CHANGELOG.md pyproject.toml quota_monitor/ tests/   # plus any other files in this release
git commit -m "$(cat <<'EOF'
<type>(<scope>): <one-line summary of the release>

<one-paragraph body explaining the change and why>
EOF
)"
git tag -a vX.Y.Z -m "Release vX.Y.Z"
git push origin main
git push origin vX.Y.Z
```

Conventional-commits prefixes (`feat`, `fix`, `refactor`, `test`,
`docs`, `chore`) match `CONTRIBUTING.md`. The annotated tag (`-a`) is
what Homebrew downloads, and the GitHub Release UI populates from it.

---

## Step 3 — Publish to PyPI

```bash
find dist -type f -delete 2>/dev/null   # clean any older artifacts
python -m build                          # builds sdist + wheel into dist/
python -m twine check dist/*             # validates metadata + README rendering
python -m twine upload dist/quota_monitor-X.Y.Z-py3-none-any.whl \
                       dist/quota_monitor-X.Y.Z.tar.gz
```

`twine upload` will read `~/.pypirc` automatically. The upload prints
`View at: https://pypi.org/project/quota-monitor/X.Y.Z/` on success.

Smoke-test from outside the project venv:

```bash
deactivate
pipx run quota-monitor==X.Y.Z --version   # or use a throwaway venv
```

It should print `quota-monitor X.Y.Z`. If it errors with "no such
release," PyPI's CDN can lag by a minute — wait and retry, do not
re-upload.

---

## Step 4 — Bump the Homebrew formula

The tap lives in a separate repo: `franksde/homebrew-tap`. The formula
file is `Formula/quota-monitor.rb`. The bump is three values:
`url`, `sha256`, and the version literal in the `test do` block.

```bash
# Get the SHA of the source tarball GitHub generates for the new tag
NEW_VERSION=X.Y.Z
NEW_SHA=$(curl -sL "https://github.com/franksde/quota-monitor/archive/refs/tags/v${NEW_VERSION}.tar.gz" | shasum -a 256 | awk '{print $1}')
echo "$NEW_SHA"

# Clone the tap into a scratch dir (or reuse an existing clone)
TAP_DIR=/tmp/homebrew-tap-work
gh repo clone franksde/homebrew-tap "$TAP_DIR"
cd "$TAP_DIR"
```

Edit `Formula/quota-monitor.rb`:

```ruby
url "https://github.com/franksde/quota-monitor/archive/refs/tags/vX.Y.Z.tar.gz"
sha256 "<NEW_SHA from above>"
...
test do
  assert_match "quota-monitor X.Y.Z", shell_output("#{bin}/quota-monitor --version")
end
```

The `assert_match` string must match exactly what `quota-monitor --version`
prints in this release. Since v0.2.4 that format is `quota-monitor X.Y.Z`
(hyphen, matches the actual CLI name). Older releases used
`quota_monitor X.Y.Z` (underscore) — do not copy from a stale formula.

(Optional, locally) — build the formula from source to verify before
pushing:

```bash
brew install --build-from-source ./Formula/quota-monitor.rb
brew test quota-monitor
brew uninstall quota-monitor
```

This downloads `python@3.11` if you don't have it (~150 MB) but catches
sha mismatches, virtualenv install failures, and bad assertions before
they reach users.

Commit and push:

```bash
git add Formula/quota-monitor.rb
git commit -m "quota-monitor X.Y.Z"
git push origin main
```

The convention in homebrew taps is one terse commit line per bump
(`<formula> <version>`), not conventional-commits. Match the existing
history.

---

## Step 5 — GitHub Release page

```bash
gh release create vX.Y.Z \
  --repo franksde/quota-monitor \
  --title "vX.Y.Z" \
  --notes-from-tag
```

`--notes-from-tag` uses the annotated tag's body as the release notes.
If you want richer notes (links to PRs, screenshots), pass
`--notes-file path/to/notes.md` instead, or edit the release in the
GitHub web UI afterwards.

---

## Step 6 — Verify

```bash
# PyPI
pipx run --spec "quota-monitor==X.Y.Z" quota-monitor --version

# Homebrew (in a clean shell, no local tap override)
brew untap franksde/tap 2>/dev/null
brew install franksde/tap/quota-monitor
quota-monitor --version
brew uninstall quota-monitor

# GitHub tag & release
gh release view vX.Y.Z --repo franksde/quota-monitor
```

All three should report version X.Y.Z. If Homebrew installs the
previous version, the cache is stale — `brew update` and retry.

---

## Recovery

- **`twine upload` failed mid-batch (one file uploaded, one didn't).**
  PyPI does not allow re-uploading the same filename even if it's
  half-broken. You must bump to the next patch (X.Y.Z+1) and re-release.
  PyPI considers a version "burned" the moment any file lands.
- **Tag pushed but tests were red.** Delete the tag remotely with
  `git push --delete origin vX.Y.Z` and locally with
  `git tag -d vX.Y.Z`. Fix, then re-tag. Do this **before** any of the
  publish steps below it run — re-tagging after a PyPI upload is a
  silent landmine because the tag content will diverge from the
  uploaded artifact.
- **Wrong SHA in the formula.** Edit `Formula/quota-monitor.rb`, push
  again. Users get a SHA mismatch error until you fix it; no PyPI
  cleanup needed.
- **Formula test assertion fails on `brew test`.** Almost always the
  expected `--version` string drifted (hyphen vs underscore, or the
  version literal wasn't bumped). Look at what
  `quota-monitor --version` actually prints in this release.

---

## What lives where (for future agents)

- The CLI version string format and the `User-Agent` versions are now
  derived from `__version__` (`quota_monitor/__init__.py`). Do not
  reintroduce hand-edited version literals in
  `__main__.py` / `notifiers/*.py` — that was a bug fixed in v0.2.4.
- `quota_monitor/cloudflare_relay/` is shipped inside the Python
  package (declared in `[tool.setuptools.package-data]` in
  `pyproject.toml`). The CF relay worker source is therefore vendored
  into both the wheel and the sdist — no separate publishing step.
- The setup wizard pulls relay assets out of the installed package via
  `importlib.resources` (see `quota_monitor/cli/_wrangler.py:prepare_cf_relay_workdir`).
  If you change relay assets, they ship automatically on the next PyPI
  release.
- `~/.pypirc` is consulted by `twine` directly; the project's runtime
  `.env` (at `~/.quota-monitor/.env`) is unrelated and holds Telegram
  credentials. Never conflate the two.
