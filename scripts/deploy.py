#!/usr/bin/env python3
"""Publish the site to the gh-pages branch. Always does a fresh build with the
production base path baked in first -- never republishes a stale local-preview
dist/, since that would ship the un-prefixed-path 404 bug this whole
source/build split exists to fix.

Run `python scripts/build.py` on its own any time to preview locally with zero
git/network side effects. Only this script (deploy.py) ever touches git or
pushes anything."""

import shutil
import subprocess
import sys
from pathlib import Path

import build

REPO_ROOT = build.REPO_ROOT
DIST_DIR = build.DEFAULT_OUT_DIR
DEPLOY_BASE_PATH = "/jamesvalcourt"
BRANCH = "gh-pages"
WORKTREE_DIR = REPO_ROOT / ".deploy" / "gh-pages-worktree"


def run(args, check=True, capture=False):
    result = subprocess.run(args, cwd=REPO_ROOT, check=False,
                             capture_output=capture, text=True)
    if check and result.returncode != 0:
        stderr = result.stderr if capture else ""
        raise RuntimeError(f"Command failed: {' '.join(args)}\n{stderr}")
    return result


def remote_has_branch(branch: str) -> bool:
    result = run(["git", "ls-remote", "--exit-code", "--heads", "origin", branch], check=False)
    return result.returncode == 0


def ensure_worktree():
    run(["git", "worktree", "prune"])
    if (WORKTREE_DIR / ".git").exists():
        return  # already registered, reuse as-is

    if WORKTREE_DIR.exists():
        shutil.rmtree(WORKTREE_DIR)  # stale dir git doesn't know about

    WORKTREE_DIR.parent.mkdir(parents=True, exist_ok=True)
    if remote_has_branch(BRANCH):
        print(f"Found existing origin/{BRANCH}, checking it out into worktree...")
        run(["git", "fetch", "origin", BRANCH])
        run(["git", "worktree", "add", str(WORKTREE_DIR), f"origin/{BRANCH}", "-B", BRANCH])
    else:
        print(f"No {BRANCH} branch on origin yet -- creating it (first deploy).")
        run(["git", "worktree", "add", "--orphan", "-b", BRANCH, str(WORKTREE_DIR)])


def sync_worktree_with_dist():
    # Clear everything currently tracked, then repopulate from dist/. Handles
    # deletions/renames cleanly (e.g. a blog post slug changed since last deploy).
    run(["git", "-C", str(WORKTREE_DIR), "rm", "-rf", "--quiet", "."], check=False)
    for item in DIST_DIR.iterdir():
        dest = WORKTREE_DIR / item.name
        if item.is_dir():
            shutil.copytree(item, dest, dirs_exist_ok=True)
        else:
            shutil.copy2(item, dest)


def publish():
    is_first_deploy = not remote_has_branch(BRANCH)

    print(f"Building with base_path={DEPLOY_BASE_PATH!r}...")
    build.build_site(base_path=DEPLOY_BASE_PATH, out_dir=DIST_DIR)
    (DIST_DIR / ".nojekyll").touch()

    ensure_worktree()
    sync_worktree_with_dist()

    run(["git", "-C", str(WORKTREE_DIR), "add", "-A"])
    status = run(["git", "-C", str(WORKTREE_DIR), "status", "--porcelain"], capture=True)
    if not status.stdout.strip():
        print("Nothing changed since the last deploy -- skipping commit/push.")
        return

    sha = run(["git", "rev-parse", "--short", "HEAD"], capture=True).stdout.strip()
    run(["git", "-C", str(WORKTREE_DIR), "commit", "-m", f"Deploy site from main@{sha}"])
    run(["git", "-C", str(WORKTREE_DIR), "push", "origin", f"HEAD:{BRANCH}"])
    print(f"\nPushed to origin/{BRANCH}.")

    if is_first_deploy:
        print(
            "\nFirst deploy done. One-time manual step required:\n"
            "  GitHub repo -> Settings -> Pages -> Source: 'Deploy from a branch'\n"
            f"  Branch: {BRANCH} / (root)\n"
            "  (equivalent: gh api -X PUT repos/jrvalcourt/jamesvalcourt/pages "
            f"-f source[branch]={BRANCH} -f 'source[path]=/')"
        )


if __name__ == "__main__":
    try:
        publish()
    except RuntimeError as e:
        print(f"error: {e}", file=sys.stderr)
        sys.exit(1)
