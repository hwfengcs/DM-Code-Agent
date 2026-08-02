# 32 — User-level config and `.env`: making a global install actually work

## TL;DR

Three bugs made `pip install dm-code-agent` unusable outside a cloned repo, and all three
were **invisible under editable installs**. Config was written to `site-packages/`, the
user's `.env` was never found, and the missing-key error told you to "set an environment
variable" without saying where. Fixed by routing every path through a new
`dm_agent/paths.py`, with lookup order `./X` → `~/.dm_agent/X` for both `config.json`
and `.env`. Writes go back to whichever file was read.

## Context

The project has shipped a complete distribution story for a while without anyone noticing:
`[project.scripts]` declares seven entry points, `package-data` bundles the built frontend
into the wheel, and CI verifies the committed artifacts match source. An end-to-end check
confirmed it works — a 533 KB wheel installs into a clean venv, all seven commands appear,
`dm-agent-web` serves the React UI at `GET /` with no Node and no clone.

But `DISTRIBUTION_CHECKLIST.md` planned GitHub releases, blog posts, and awesome-list
submissions — and **no PyPI publish**. Its demo script still opened with
`pip install -e ".[dev]"`. The mental model throughout was "users clone the repo," and the
code had quietly outgrown it.

That assumption hid three bugs, each of which only fires when the package lives somewhere
other than the working directory.

## The three bugs

### P0 — config written into `site-packages/`

```python
CONFIG_FILE = str(Path(__file__).resolve().parents[2] / "config.json")
```

Under `pip install -e`, `parents[2]` from `dm_agent/cli/config.py` is the repo root — correct,
and indistinguishable from correct. Under a real install it is `site-packages/`. Consequences:
polluting another package's install root, hard failure on read-only or system Python installs,
one shared config across every project, and a file the user cannot locate.

The comment above that line said the path was chosen to stay consistent with the historical
top-level `main.py`. That was a faithful description of a design that had stopped being valid.

### P1 — the user's `.env` is unreachable

`load_dotenv()` with no arguments calls `find_dotenv(usecwd=False)`, which searches upward
**from the calling module's directory**. Installed, that walk starts at
`site-packages/dm_agent/cli/` and never reaches the user's project. A `.env` placed next to
the code being worked on silently does nothing.

There is a nice irony here: `tests/conftest.py` already documented this function's behaviour,
discovered when an early Web-console test really spent money by picking up the repo-root
`.env` from a subprocess whose cwd was elsewhere. Same mechanism, opposite symptom — under
editable install it finds too much, under a real install too little.

### P2 — an error you cannot act on

`请提供 --api-key 或设置环境变量 DEEPSEEK_API_KEY。` Fine when you are sitting in a repo with
`.env.example` next to you. Useless after `pip install`, where the question is *which file,
in which directory*.

## Design

New `dm_agent/paths.py`, dependency-free and at the bottom of the layer graph.

**Why not `cli/`**: `server/cli.py` needs the same `.env` loading, and server must not import
cli (`tests/test_server_layering.py` asserts this via AST, because `dm_agent/server/**` is
exempt from `TID251` and ruff cannot catch it). A module importing only `pathlib`/`os`/`dotenv`
is safe for every layer.

**Lookup order** — project first, user second, for both files:

```
./config.json              →  ~/.dm_agent/config.json
./.env                     →  ~/.dm_agent/.env
```

`~/.dm_agent/` was already the home for `extensions/` and `trusted-projects.json`; adding two
files there beats introducing a second convention via `platformdirs`.

**Writes go back to the file that was read.** The alternative — always write user-level — 
produces "I changed the setting and nothing happened" whenever a project-level config exists.
This choice also happens to make the change **behaviour-preserving for existing users**: anyone
running from a cloned repo reads and writes the repo-root `config.json` exactly as before, so
no migration logic is needed.

**`override=False` everywhere**, which is dotenv's default. Priority becomes
`exported env var > ./.env > ~/.dm_agent/.env`. This is not incidental: `conftest.py`'s
`block_real_api_keys` fixture depends on exactly this semantics to guarantee tests cannot
spend money.

## What was deliberately not done

- **`trust.py`'s atomic write was not extracted.** `paths.atomic_write_json` duplicates its
  tempfile → fsync → `os.replace` → chmod sequence. Merging them is a refactor, and the
  constitution's rule that refactors must not carry fixes reads the same in reverse. Worth
  unifying later; not in a commit whose correctness argument is "these three bugs are gone."
- **No `dm-agent init`.** Better first-run UX, but a new feature, and P2's actual defect is
  that the message lacks paths.
- **`mcp_config.json` untouched.** It already resolves against cwd, which is right.
- **No auto-migration.** See above — the repo-root case is byte-for-byte unchanged.

## Testing

`tests/test_cli_config_paths.py`, 15 cases. The load-bearing one:

```python
def test_config_paths_never_land_inside_the_package(tmp_path):
    package_dir = Path(paths.__file__).resolve().parent
    for candidate in (...):
        assert package_dir not in candidate.resolve().parents
```

This is the regression guard for P0 and it works under editable installs too, since it
compares against the package directory wherever that happens to be.

A second change matters more than it looks: `conftest.py` gained an autouse
`isolate_user_home` fixture redirecting `HOME` **and** `USERPROFILE` (Windows `Path.home()`
reads the latter) into a factory-provided tmp dir. Without it, `parse_args()` → 
`load_config_from_file()` now reaches `~/.dm_agent/config.json`, and **every test's behaviour
would depend on whether the machine running them happens to have that file** — the classic
green-locally/red-in-CI setup. It uses `tmp_path_factory` rather than `tmp_path` because
tests build their own `home/` directories inside `tmp_path`.

468 → 483 tests, all passing.

## Verification

Beyond the CI-equivalent suite, the acceptance test is one only reproducible outside the repo:
build a wheel, install it into a clean venv, run from an unrelated directory, then assert
`site-packages/config.json` does not exist, config lands in `~/.dm_agent/config.json`, and a
local `./.env` is honoured. Those three are precisely the failure surfaces of P0 and P1, and
none of them is observable from inside a checkout.

## A fourth bug, found by the verification itself

The acceptance test creates a `.env` the way a Windows user naturally would —
`Set-Content -Encoding utf8` — and the key still did not load, even though the file was
correctly *found*. PowerShell writes a UTF-8 BOM, dotenv reads as plain `utf-8`, and the BOM
ends up inside the first key name: the environment gets `﻿DEEPSEEK_API_KEY` and the CLI still
reports "missing API key."

This is worth calling out because it is exactly the failure mode P1 and P2 were meant to
eliminate — the user has configured the key, and the tool insists they have not — and it is
essentially undiagnosable without hexdumping the file. Every common way to produce a `.env`
on Windows writes a BOM: `Set-Content -Encoding utf8`, `>` redirection, Notepad's "UTF-8"
save. The freshly written docs would have walked users straight into it.

Fix is one argument: read as `utf-8-sig`, which strips a BOM when present and is byte-for-byte
`utf-8` otherwise. It was in scope because it sits on the same user journey with the same
symptom, not because it was in the original plan.

The general lesson: the acceptance test caught this precisely *because* it simulated the
user's environment rather than asserting on internals. A test that wrote the fixture with
Python's `write_text` would have passed and shipped the bug.

## Open questions / next bets

- **Publish to PyPI.** The name `dm-code-agent` is unclaimed. These fixes are its
  prerequisite: a PyPI version number cannot be reused, so shipping `2.0.0` with a
  config writer aimed at `site-packages/` would strand the first users on a broken release
  that stays public forever.
- **Trusted Publishing via GitHub Actions** (OIDC, no stored token), so a tag push releases.
- **Unify the two atomic-write implementations** in a standalone refactor commit.
- **Reduce the install floor further** — an `npx`-style wrapper or a one-line install script —
  only after real users report where they actually get stuck.
