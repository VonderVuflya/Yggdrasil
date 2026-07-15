---
description: Distill your recent work into durable Yggdrasil memory (local)
argument-hint: [extra flags, e.g. --dry-run or --force]
---
Run `ygg seed $ARGUMENTS` via Bash (fall back to `uvx --from yggdrasil-memory ygg seed $ARGUMENTS` if `ygg` isn't on PATH). This discovers your Claude Code / Codex transcripts, Obsidian vaults and repos, and distills them into atomic lessons **locally** — nothing leaves the machine.

Before running the real thing, prefer showing the estimate first: if the user gave no arguments, run with `--dry-run` and report how many files/sources would be distilled and the rough time, then ask whether to proceed. Summarize the result: lessons added, merged, truncated-dropped, and anything that timed out (with the suggested `--timeout` bump).
