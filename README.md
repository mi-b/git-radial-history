# git-radial-history

Turn any Git repository into a radial history poster: one self-contained SVG and
a PNG rendered from it, entirely offline.

Each calendar year becomes a concentric ring, days advance clockwise from twelve
o'clock, and the area of each circle encodes the net lines changed that day.
Release tags appear as radial triangles. The first commit sits in the centre.

The tool drives the installed `git` executable directly — no provider APIs, no
Python Git reimplementation — so it works with GitHub, GitLab, self-hosted
servers, and plain Git remotes alike.

## Example

Git's own history, visualised by this tool:

<p align="center">
  <img src="docs/git-history-of-git.png" alt="Radial history poster of the Git repository" width="600">
</p>

The PNG above is a preview; the crisp, self-contained
[SVG version](docs/git-history-of-git.svg) is the canonical output.

## Installation

Requires [`uv`](https://docs.astral.sh/uv/) and a `git` executable on your
`PATH`. `uv` fetches a suitable Python interpreter automatically, so you do not
need one installed already.

```bash
# Run without installing
uvx git-radial-history --help

# Install as a persistent tool
uv tool install git-radial-history
```

## Usage

Point it at a local path or a remote URL:

```bash
# Local repository
git-radial-history /path/to/repo

# GitHub (Git's default branch is master, not main)
git-radial-history https://github.com/git/git --ref master

# GitLab, with an explicit output name and only SVG
git-radial-history https://gitlab.com/gitlab-org/gitlab.git \
  --ref master --output gitlab-history --format svg
```

Progress and warnings go to standard error; the generated file paths go to
standard output, so the command slots neatly into scripts and pipelines.

```bash
poster=$(git-radial-history /path/to/repo --format svg)
echo "wrote $poster"
```

> [!NOTE]
> The first run against a large remote clones the full history and extracts every
> reachable commit's line changes — this can take a while. Subsequent runs against
> the same commit are near-instant thanks to caching (see [Caching](#caching)).

## Options

| Option | Description |
|---|---|
| `SOURCE` | Local repository path or Git remote URL (required). |
| `--ref REF` | Revision or branch to analyse. Default: `HEAD`. |
| `--output PATH` | Output basename (without extension). Default: the repository name. |
| `--format svg\|png\|both` | Which files to write. Default: `both`. |
| `--config PATH` | Read visual settings from a TOML file (see [Configuration](#configuration)). |
| `--tags major\|minor\|patch` | Lowest release level to show, and everything above it. Default: `minor`. |
| `--title TEXT` | Override the inferred repository name shown in the centre. |
| `--refresh` | Re-fetch an already-cached remote to pick up new commits. |
| `--from DATE` | Ignore activity before this date (`YYYY-MM-DD`). |
| `--until DATE` | Ignore activity after this date (`YYYY-MM-DD`). |
| `--scale N` | Multiply the PNG raster resolution by `N` for larger exports. |
| `--version` | Print the version and exit. |

### Selecting which tags to show

Projects that backport fixes across many maintenance branches (Git itself is the
classic offender) tag a dozen releases on a single day, which turns the poster
into a triangle blizzard. The `--tags` flag sets a threshold:

| `--tags` | Shows |
|---|---|
| `major` | Major releases only (e.g. `v2.0.0`). |
| `minor` | Major and minor releases. This is the default. |
| `patch` | Everything, including backported patch releases. |

Release candidates and pre-releases (`-rc1`, `-alpha`, `-beta`) are hidden unless
you enable them in configuration. For git/git this cuts the visible tags from
several hundred down to a readable handful.

## Visual encoding

| Data | Representation |
|---|---|
| Calendar year | One concentric ring (innermost = oldest). |
| Day within the year | Clockwise angle, January at twelve o'clock. |
| Positive net change | Filled circle. |
| Negative net change | Outlined circle. |
| Zero-net active day | Small neutral dot. |
| Magnitude of change | Circle area (square-root scaled). |
| Release tag | Radial triangle: solid = major, outlined = minor/patch. |
| First commit | Central annotation with the repository name and date range. |

Only active days receive markers. Inactive days stay blank rather than implying
work that never happened.

## Configuration

Visual settings load from a TOML file passed with `--config`. Unknown sections
and keys are rejected, so a typo fails loudly instead of being silently ignored.

The defaults use a [Catppuccin Mocha](https://catppuccin.com/) palette:

```toml
[poster]
width = 2400
height = 2400
background = "#1e1e2e"   # base
positive = "#b4befe"     # additions (lavender)
negative = "#f5e0dc"     # removals (rosewater)
accent = "#f38ba8"       # release tags (red)
text = "#cdd6f4"
show_year_labels = false

[layout]
inner_radius_ratio = 0.28
outer_radius_ratio = 0.90
chart_height_ratio = 1.0

[scale]
percentile = 99          # reference magnitude for circle scaling
maximum_radius = 0       # 0 = no cap; otherwise clip and disclose in the legend

[tags]
show = true
show_unrecognised = false   # show non-semver tags
show_prerelease = false     # show -rc / -alpha / -beta tags
levels = ["major", "minor", "patch"]
```

Settings are resolved in this order, later winning:

```text
built-in defaults  <  --config TOML file  <  explicit CLI flags
```

So `--tags major` overrides a `levels` list from a config file, and both override
the built-in default.

### Ready-made variants

Alternative palettes live in [`themes/`](themes/) and are just config files:

```bash
git-radial-history /path/to/repo --config themes/macchiato.toml
git-radial-history /path/to/repo --config themes/mocha-alt.toml
```

## Caching

Two independent caches live under your platform cache directory:

- A **bare-repository cache**, keyed by the sanitised remote URL and branch.
- An **analysis cache**, keyed by the resolved commit hash and schema version.

Re-running against a commit that has already been analysed skips both the network
fetch and the diff extraction. Changing colours, dimensions, or the tag threshold
never triggers another history scan — only the render is repeated.

Use `--refresh` to re-fetch a cached remote and pick up new commits.

## Private repositories

Authentication is delegated to your existing Git credential helpers and SSH
configuration. HTTPS URLs with embedded credentials are rejected, and credentials
never appear in cache keys, metadata, logs, or error messages.

## Limitations

- Shallow clones are refused, because the history — and therefore the poster —
  would be incomplete.
- Binary files are excluded from line counts; their presence is reported as a
  warning.
- Submodules are not analysed.
- PNG output requires the `resvg-py` package.

## Reproducibility

For a given commit and configuration the SVG is deterministic and
self-contained: no generation timestamps, stable element ordering, and consistent
number formatting, so version-controlled posters produce meaningful diffs.

## Acknowledgements

This project is a homage to Jeff Palmer's
[radial visualisation of Git's change history](https://jpalmer.dev/2021/03/visualizing-the-change-history-of-the-git-repository/).
The design follows the visual rules described and shown in that
article.

This implementation is original and independent. No code from the original was copied
(which was never published).
If you like this, go and read Palmer's article — it is the reason this exists.

## Licence

MIT. See [LICENSE.md](LICENSE.md).
