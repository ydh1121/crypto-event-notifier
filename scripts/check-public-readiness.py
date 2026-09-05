from __future__ import annotations

import re
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

# Files that must never be tracked in a public repository. Keep this list focused
# on actual local runtime/secrets; examples and ordinary deploy manifests are
# reviewed separately below instead of treated as blockers.
BLOCKING_PATH_PATTERNS = (
    re.compile(r"(^|/)\.env$", re.I),
    re.compile(r"(^|/)\.env\.(?!example$)[^/]+$", re.I),
    re.compile(r"(^|/)b3_trader/data/", re.I),
    re.compile(r"\.sqlite3?(?:$|[-.])", re.I),
    re.compile(r"(^|/)dashboard/runtime-demo(?:-upbit)?\.json$", re.I),
    re.compile(r"(^|/)dashboard/demo-runtime(?:-upbit)?/", re.I),
    re.compile(r"(^|/)cloudflare-pages/wrangler\.local\.jsonc$", re.I),
    re.compile(r"(^|/)cloudflare-pages/wrangler\.jsonc$", re.I),
    re.compile(r"(^|/)cloudflare/.*wrangler\.local\.jsonc$", re.I),
)

REVIEW_PATH_PATTERNS = (
    re.compile(r"(^|/)\.env\.example$", re.I),
    re.compile(r"(^|/)cloudflare/wrangler\.jsonc$", re.I),
)

SECRET_PATTERNS = (
    r"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----",
    r"github_pat_[A-Za-z0-9_]{20,}",
    r"gh[pousr]_[A-Za-z0-9]{20,}",
    r"AKIA[0-9A-Z]{16}",
    r"xox[baprs]-[A-Za-z0-9-]{10,}",
    r"sk-[A-Za-z0-9_-]{20,}",
    r"CLOUDFLARE_(?:API_TOKEN|VIEWER_INGEST_TOKEN|VIEWER_BOOTSTRAP_TOKEN|ACCOUNT_ID)\s*[:=]\s*[^\s'\"]{12,}",
    r"OWNER_BOOTSTRAP_TOKEN\s*[:=]\s*[^\s'\"]{12,}",
    r"INGEST_TOKEN\s*[:=]\s*[^\s'\"]{12,}",
    r"TELEGRAM_(?:BOT_)?TOKEN\s*[:=]\s*[^\s'\"]{12,}",
    r"BITHUMB_(?:ACCESS|SECRET)_KEY\s*[:=]\s*[^\s'\"]{12,}",
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


def matching(paths: list[str], patterns: tuple[re.Pattern[str], ...]) -> list[str]:
    return sorted({path for path in paths if any(pattern.search(path) for pattern in patterns)})


def main() -> None:
    print("=== PUBLIC REPOSITORY READINESS ===")

    tracked_now = lines("ls-files")
    history_names = lines("log", "--all", "--name-only", "--pretty=format:")
    current_blocking = matching(tracked_now, BLOCKING_PATH_PATTERNS)
    historical_blocking = matching(history_names, BLOCKING_PATH_PATTERNS)
    current_review = matching(tracked_now, REVIEW_PATH_PATTERNS)
    historical_review = matching(history_names, REVIEW_PATH_PATTERNS)

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

    print(f"tracked_blocking_paths={len(current_blocking)}")
    for path in current_blocking:
        print(f"  CURRENT_BLOCKER: {path}")

    print(f"historical_blocking_paths={len(historical_blocking)}")
    for path in historical_blocking:
        print(f"  HISTORY_BLOCKER: {path}")

    print(f"review_config_paths={len(current_review)}")
    for path in current_review:
        print(f"  REVIEW_PATH: {path}")
    if historical_review:
        print(f"historical_review_paths={len(historical_review)}")

    print(f"secret_pattern_files={len(secret_hits)}")
    for path, refs in sorted(secret_hits.items()):
        print(f"  SECRET_PATTERN: {path} commits={','.join(sorted(refs)[:8])}")

    print(f"non_noreply_author_emails={len(public_emails)}")
    if public_emails:
        print("  NOTE: commit author email metadata will be visible after making the repository public.")

    print("actions_history_manual_check=REQUIRED")
    print("  NOTE: old Actions logs/artifacts become part of the public repository surface; rotate any secret that may ever have been handed off as an artifact.")

    blockers: list[str] = []
    if current_blocking:
        blockers.append("actual runtime/secret paths are currently tracked")
    if historical_blocking:
        blockers.append("actual runtime/secret paths exist in Git history")
    if secret_hits:
        blockers.append("secret-like value patterns exist in Git history")

    print("\n=== RESULT ===")
    if blockers:
        for item in blockers:
            print(f"BLOCKER: {item}")
        print("PUBLIC_READINESS=BLOCKED")
        raise SystemExit(1)

    if current_review:
        print("REVIEW: example/general config files are tracked; inspected separately, not secret blockers")
    if public_emails:
        print("WARNING: non-noreply commit author email metadata exists")
    print("WARNING: review old Actions history; safest path is to rotate Cloudflare viewer machine/bootstrap secrets before visibility change")
    print("PUBLIC_READINESS=REVIEW")


if __name__ == "__main__":
    main()
