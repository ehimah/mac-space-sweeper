# Contributing

Thanks for contributing.

This project deals with filesystem cleanup, so correctness matters more than novelty. A cleanup bug can delete something valuable. Keep changes conservative, explicit, and easy to audit.

## Local setup

```bash
git clone <your-fork-or-repo-url>
cd mac-space-sweeper
npm install
npm run build
```

Verify the project before opening a pull request:

```bash
npm run check
```

## Development workflow

1. Create a branch for your change.
2. Make the smallest change that solves the problem.
3. Prefer `--dry-run` while testing cleanup behavior.
4. Run `npm run check`.
5. Update `README.md` if the user workflow changes.

## Project structure

- `scripts/mac_junk_cleaner.py`: scanning, categorization, JSON output, and direct cleanup logic
- `source/`: Ink/Pastel terminal UI
- `source/lib/backend.ts`: bridge from the TUI to the Python backend

## Contribution guidelines

### If you add or change a cleanup category

Document:

- the paths covered
- why the files are considered disposable
- any overlap with existing categories
- any permission or safety caveats

Prefer category rules that are:

- easy to explain
- common on macOS systems
- reversible in practice because the target is recreatable cache or log data

Avoid category rules that:

- target user documents by default
- assume app-specific internal knowledge without documentation
- require elevated privileges just to function

### If you change cleanup behavior

Be explicit about:

- whether deletion is permanent
- whether symlinks are handled safely
- how progress and errors are surfaced to the user

### If you change the TUI

Preserve:

- a safe dry-run-first workflow
- clear visibility into what is selected
- progress reporting during cleanup

## Pull request checklist

- `npm run check` passes
- README updates are included when needed
- no generated artifacts are committed unless there is a strong reason
- new cleanup logic is conservative and documented
- any destructive behavior changes are called out clearly in the PR description

## Reporting bugs

Bug reports are most useful when they include:

- macOS version
- Node.js version
- Python version
- the command used
- the affected category
- a redacted error message or screenshot
