from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

SENSITIVE_PATH_PATTERNS = (
    re.compile(r"(^|/)\.env($|\.)", re.I),
    re.compile(r"(^|/)b3_trader/data/", re.I),
    re.compile(r"\.sqlite3?(?:$|[-.])", re.I),
    re.compile(r"(^|/)dashboard/runtime-demo(?:-upbit)?\.json$", re.I),
    re.compile(r"(^|/)cloudflare-pages/wrangler(?:\.local)?\.jsonc$", re.I),
    re.compile(r"(^|/)cloudflare/wrangler(?:\.local)?\.jsonc$", re.I),
)

SECRET_PATTERNS = (
    r"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----",
    r"github_pat_[A-Za-z0-9_]{20,}",
    r"gh[pousr]_[A-Za-z0-9]{20,}",
    r"AKIA[0-9A-Z]{16}",
    r"xox[baprs]-[A-Za-z0-9-]{10,}",
    r"sk-[A-Za-z0-9_-]{20,}",
    r"CLOUDFLARE_(?:API_TOKEN|VIEWER_INGEST_TOKEN|VIEWER_BOOTSTRAP_TOKEN)\s*[:=]\s*[^\s'\"]{12,}",
    r"TELEGRAM_(?:BOT_)?TOKEN\s*[:=]\s*[^\s'\"]{12,}",
)
SECRET_REGEX = "(?:" + ")|(?:".join(SECRET_PATTERNS) + ")"


def run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args], cwd=REPO_ROOT, capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=120, check=False,
    )


def lines(*args: str) -> list[str]:
    result = run(*args)
    if result.returncode != 0:
        return []
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def main() -> None:
    print("=== PUBLIC REPOSITORY READINESS ===")

    tracked_now = lines("ls-files")
    current_sensitive = sorted({
        path for path in tracked_now
        if any(pattern.search(path) for pattern in SENSITIVE_PATH_PATTERNS)
    })

    history_names = lines("log", "--all", "--name-only", "--pretty=format:")
    historical_sensitive = sorted({
        path for path in history_names
        if any(pattern.search(path) for pattern in SENSITIVE_PATH_PATTERNS)
    })

    commits = lines("rev-list", "--all")
    secret_hits: dict[str, set[str]] = {}
    for commit in commits:
        result = run("grep", "-I", "-l", "-E", SECRET_REGEX, commit, "--")
        if result.returncode not in {0, 1}:
            continue
        for path in result.stdout.splitlines():
            path = path.strip()
            if path:
                secret_hits.setdefault(path, set()).add(commit[:7])

    emails = sorted(set(lines("log", "--all", "--format=%ae")))
    public_emails = [email for email in emails if email and "noreply.github.com" not in email.lower()]

    print(f"tracked_sensitive_paths={len(current_sensitive)}")
    for path in current_sensitive:
        print(f"  CURRENT_PATH: {path}")

    print(f"historical_sensitive_paths={len(historical_sensitive)}")
    for path in historical_sensitive:
        print(f"  HISTORY_PATH: {path}")

    print(f"secret_pattern_files={len(secret_hits)}")
    for path, refs in sorted(secret_hits.items()):
        print(f"  SECRET_PATTERN: {path} commits={','.join(sorted(refs)[:8])}")

    print(f"non_noreply_author_emails={len(public_emails)}")
    if public_emails:
        print("  NOTE: commit author email metadata will be visible after making the repository public.")

    print("actions_history_manual_check=REQUIRED")
    print("  NOTE: GitHub states that existing Actions history/logs become visible when a private repository is made public.")

    blockers: list[str] = []
    if current_sensitive:
        blockers.append("sensitive runtime/config paths are currently tracked")
    if historical_sensitive:
        blockers.append("sensitive runtime/config paths exist in Git history")
    if secret_hits:
        blockers.append("secret-like value patterns exist in Git history")

    print("\n=== RESULT ===")
    if blockers:
        for item in blockers:
            print(f"BLOCKER: {item}")
        print("PUBLIC_READINESS=BLOCKED")
        raise SystemExit(1)

    if public_emails:
        print("WARNING: non-noreply commit author email metadata exists")
    print("WARNING: review/delete any sensitive old Actions logs/artifacts before visibility change")
    print("PUBLIC_READINESS=REVIEW")


if __name__ == "__main__":
    main()
