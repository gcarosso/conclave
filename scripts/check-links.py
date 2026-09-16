#!/usr/bin/env python3
"""Check relative links and anchors in the repository's Markdown files.

  python3 scripts/check-links.py [ROOT]

For every [text](target) outside code: external schemes (http, https, mailto) are skipped; a relative path must
exist; a #anchor must match a heading slug in the target Markdown file (GitHub's slug rules, duplicates suffixed
-1, -2). A trailing :<line> on a path is ignored. Exit status is the number of broken links (capped at 100).
"""
import os
import re
import subprocess
import sys

LINK = re.compile(r"!?\[[^\]]*\]\(\s*<?([^)\s>]+)>?(?:\s+\"[^\"]*\")?\s*\)")
HEADING = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
FENCE = re.compile(r"^\s*(```|~~~)")


def md_files(root):
    try:
        out = subprocess.run(["git", "-C", root, "ls-files", "--cached", "--others", "--exclude-standard", "*.md"],
                             capture_output=True, text=True, check=True).stdout.split()
        return [os.path.join(root, p) for p in out if os.path.exists(os.path.join(root, p))]
    except Exception:
        found = []
        for d, dirs, files in os.walk(root):
            dirs[:] = [x for x in dirs if x != ".git"]
            found += [os.path.join(d, f) for f in files if f.endswith(".md")]
        return found


def prose_lines(path):
    """Yield (line number, text) outside fenced code blocks, with inline code spans blanked."""
    fenced = False
    with open(path, encoding="utf-8") as f:
        for n, line in enumerate(f, 1):
            if FENCE.match(line):
                fenced = not fenced
                continue
            if not fenced:
                yield n, re.sub(r"`[^`]*`", lambda m: " " * len(m.group(0)), line)


def slugs(path):
    seen, out = {}, set()
    for _, line in prose_lines(path):
        m = HEADING.match(line)
        if not m:
            continue
        text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", m.group(2))
        s = re.sub(r"[^\w\- ]", "", text.strip().lower()).replace(" ", "-")
        k = seen.get(s, 0)
        out.add(s if k == 0 else "%s-%d" % (s, k))
        seen[s] = k + 1
    return out


def main():
    root = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(__file__), ".."))
    cache, broken, checked = {}, 0, 0
    for md in sorted(md_files(root)):
        for n, line in prose_lines(md):
            for target in LINK.findall(line):
                if re.match(r"^[a-z][a-z0-9+.-]*:", target, re.I):
                    continue
                checked += 1
                path, _, anchor = target.partition("#")
                path = re.sub(r":\d+(-\d+)?$", "", path)
                dest = md if not path else os.path.normpath(os.path.join(os.path.dirname(md), path))
                rel = os.path.relpath(md, root)
                if not os.path.exists(dest):
                    print("%s:%d: %s — no such file" % (rel, n, target))
                    broken += 1
                    continue
                if anchor and dest.endswith(".md"):
                    if dest not in cache:
                        cache[dest] = slugs(dest)
                    if anchor.lower() not in cache[dest]:
                        print("%s:%d: %s — no heading #%s in %s" % (rel, n, target, anchor, os.path.relpath(dest, root)))
                        broken += 1
    print("links: %d relative links checked, %d broken" % (checked, broken))
    return min(broken, 100)


if __name__ == "__main__":
    sys.exit(main())
