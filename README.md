# Mac Space Sweeper

Interactive macOS disk cleanup with a conservative Python scanner and an Ink/Pastel terminal UI.

The project is designed as an open replacement for “junk file” scanners that show large cache, log, browser, Xcode, and download-heavy folders but hide cleanup behind a paid license. It does two things:

- scans common space-heavy categories on macOS
- lets you review and clean selected categories with live progress in the terminal

## What it scans

- user cache files in `~/Library/Caches`
- browser caches for Chrome, Firefox, Safari, Arc, Brave, and Chromium
- Xcode junk such as `DerivedData`, simulators, archives, and device support files
- system caches and logs
- user logs
- top-level downloads
- unused `.dmg` files
- screenshots and screen recordings in common locations
- Apple Mail downloads and attachment storage
- Trash contents

## Why the project is split

- `scripts/mac_junk_cleaner.py`: filesystem scanner and category logic
- `source/`: Ink/Pastel terminal UI

This keeps the filesystem logic simple and portable while making the cleanup flow interactive and easy to monitor.

## Safety model

- scanning is read-only
- cleanup is opt-in
- category overlaps are de-duplicated before cleanup
- `--dry-run` lets you verify what would happen before any deletion

Important:
live cleanup currently performs permanent deletion. Start with `--dry-run`.

## Requirements

- macOS
- `python3`
- Node.js `>=16.13`
- npm

The current dependency versions are pinned so the TUI works on Node 16 as well as newer runtimes.

## Quick start

### 1. Clone

```bash
git clone git@github.com:ehimah/mac-space-sweeper.git
cd mac-space-sweeper
```

### 2. Install dependencies

```bash
npm install
```

### 3. Build the TUI

```bash
npm run build
```

### 4. Run a safe review pass

```bash
npm start -- --dry-run
```

## Terminal controls

- `Up` / `Down`: move between categories
- `Space`: toggle the current category
- `a`: select all categories
- `r`: reset selection to recommended categories
- `d`: toggle dry-run mode
- `c` or `Enter`: start cleanup
- `q`: quit

## Common commands

Run the TUI in dry-run mode:

```bash
npm start -- --dry-run
```

Preselect everything:

```bash
npm start -- --all --dry-run
```

Preselect specific categories:

```bash
npm start -- --category user-cache --category browser-cache --dry-run
```

Show more items in the review panel:

```bash
npm start -- --dry-run --limit 10
```

Run the Python scanner directly:

```bash
python3 scripts/mac_junk_cleaner.py scan --all --show-items
```

Get machine-readable JSON from the Python backend:

```bash
python3 scripts/mac_junk_cleaner.py scan-json --all
```

## Project layout

```text
.
├── package.json
├── scripts/
│   └── mac_junk_cleaner.py
├── source/
│   ├── cli.ts
│   ├── commands/
│   └── lib/
└── tsconfig.json
```

## Development

Install and build:

```bash
npm install
npm run build
```

Run a basic verification pass:

```bash
npm run check
```

## Roadmap

- optional move-to-Trash mode instead of permanent deletion
- progress reporting for the scan phase, not just cleanup
- per-item skip/confirm during cleanup
- better handling of protected system paths and permission warnings

## Contributing

Contributions are welcome. Start with [CONTRIBUTING.md](./CONTRIBUTING.md) for setup, workflow, and safety expectations.

If you are proposing a cleanup rule, explain:

- why the target is safe to delete
- how a user can recreate it if needed
- whether it overlaps another category

## Known limitations

- this is macOS-specific
- some protected system locations may be visible during scanning but not removable without elevated privileges
- category totals can be large, but de-duplicated cleanup totals are the important number
- no move-to-Trash mode yet
