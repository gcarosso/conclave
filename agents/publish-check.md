---
name: publish-check
description: Scan files or Git objects for configured private markers using the publication gate.
---

# Publication check

Use `_system/gate/publish-check.sh` for a file, stdin, textual diff, or directory:

- `--file FILE`: scan one file.
- `--stdin`: scan supplied text.
- `--diff`: scan the staged textual diff, or the unstaged diff when nothing is staged.
- `DIR`: scan a directory tree.

For publication, use `_system/gate/publish-gate.sh --staged REPO` or `--diff REPO RANGE` to inspect Git blobs, including binaries. The wrapper's textual-diff mode does not provide that coverage.

Markers come from `--markers FILE`, `PUBLISH_GATE_MARKERS`, the target's `.publish-gate-markers`, or `_system/gate/markers.txt`. Exact-line exceptions are in the target's `.publish-gate-allow`.

Report the mode, scope, exit status, and findings. A clean result means no configured pattern matched the scanned bytes. Do not describe it as proof that the material contains no sensitive content. A missing marker file or scan error blocks publication; resolve it before continuing.
