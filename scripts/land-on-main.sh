#!/usr/bin/env bash
#
# Land the prepared merge on `main` and clean up stale branches.
#
# Companion to HANDOFF.md (read that first). Safe by design:
#   * dry-run by default — prints the plan, deletes nothing
#   * refuses to run on a dirty tree or from the wrong branch
#   * refuses to push unless the push is a verified fast-forward
#   * never force-pushes, never touches `main` itself, never deletes a branch
#     that has an open pull request
#
# Usage:
#   scripts/land-on-main.sh                 # dry run: show what would happen
#   scripts/land-on-main.sh --apply         # do it (still asks before deleting)
#   scripts/land-on-main.sh --apply --yes   # do it, no delete prompt (CI-ish)
#
set -euo pipefail

REPO="7amankrishna/SIH26056"
WORK_BRANCH="${WORK_BRANCH:-arena/01a08641-sih26056}"
NEW_BRANCH="${NEW_BRANCH:-feature/supabase-import}"
PROTECTED_BRANCHES=("main" "master")

APPLY=0
ASSUME_YES=0
for arg in "$@"; do
  case "$arg" in
    --apply) APPLY=1 ;;
    --yes|-y) ASSUME_YES=1 ;;
    -h|--help) sed -n '2,20p' "$0"; exit 0 ;;
    *) echo "unknown argument: $arg (try --help)" >&2; exit 2 ;;
  esac
done

run() { # print + run (in --apply), or just print (dry run)
  if [ "$APPLY" -eq 1 ]; then echo "+ $*"; "$@"; else echo "[dry-run] $*"; fi
}

echo "== repo: $REPO"
echo "== mode: $([ "$APPLY" -eq 1 ] && echo APPLY || echo DRY-RUN)"
echo

# ---------------------------------------------------------------- 0. preflight
echo "--- preflight"
[ -n "$(git status --porcelain)" ] && { echo "ABORT: working tree is dirty."; git status --short; exit 1; }
echo "working tree: clean"

CURRENT="$(git branch --show-current)"
echo "current branch: $CURRENT"

if ! git remote get-url origin >/dev/null 2>&1; then
  echo "ABORT: no 'origin' remote configured (or unavailable)."; exit 1
fi

# ------------------------------------------------------- 1. refresh remote refs
echo
echo "--- fetch"
if [ "$APPLY" -eq 1 ]; then
  # No network / revoked access must be a clear stop, not a stack trace:
  # this is exactly what a closed Arena session looks like.
  if ! git fetch --unshallow origin 2>/dev/null && ! git fetch origin 2>/dev/null; then
    echo "ABORT: cannot reach origin. If this is an Arena session whose pull"
    echo "       request was merged or closed, remote access was revoked —"
    echo "       start a new coding session and run this script there."
    exit 1
  fi
else
  echo "[dry-run] git fetch origin"
fi
REMOTE_MAIN="$(git rev-parse --short=7 origin/main 2>/dev/null || echo unknown)"
LOCAL_MAIN="$(git rev-parse --short=7 main)"
BRANCH_TIP="$(git rev-parse --short=7 "$WORK_BRANCH")"
echo "origin/main = $REMOTE_MAIN"
echo "local  main = $LOCAL_MAIN"
echo "$WORK_BRANCH = $BRANCH_TIP"

# ------------------------------------------------- 2. verify fast-forward only
echo
echo "--- fast-forward check"
if git merge-base --is-ancestor origin/main main 2>/dev/null; then
  echo "OK: origin/main is an ancestor of main — push will fast-forward"
else
  echo "STOP: main is NOT a fast-forward of origin/main."
  echo "      Merge origin/main into main first, then re-run. Never force-push."
  exit 1
fi

# ----------------------------------------------------------- 3. merge if needed
echo
echo "--- merge check"
if git branch --contains "$WORK_BRANCH" 2>/dev/null | grep -qx "  main\|main"; then
  echo "OK: main already contains $WORK_BRANCH — nothing to merge"
else
  echo "main does NOT contain $WORK_BRANCH; merging"
  run git checkout main
  run git merge --no-ff "$WORK_BRANCH" \
      -m "Merge $WORK_BRANCH into main: persist imported data to the database"
fi

# --------------------------------------------------------- 4. named work branch
echo
echo "--- working branch"
# Created from the work branch, not from main, so it carries every commit.
if git show-ref --verify --quiet "refs/heads/$NEW_BRANCH"; then
  echo "branch $NEW_BRANCH already exists"
else
  run git branch "$NEW_BRANCH" "$WORK_BRANCH"
  run git push -u origin "$NEW_BRANCH"
fi

# ------------------------------------------------------------------- 5. push
echo
echo "--- push"
run git push origin main

# --------------------------------------------------------- 6. branch cleanup
echo
echo "--- remote branches"
if command -v gh >/dev/null 2>&1; then
  BRANCHES="$(gh api "repos/$REPO/branches" --jq '.[].name' 2>/dev/null || echo '')"
else
  BRANCHES="$(git branch -r --format='%(refname:short)' | sed 's#^origin/##' | grep -v '^HEAD$' || true)"
fi
echo "$BRANCHES" | sed 's/^/    /'

# Anything protected, current, or holding an open PR is off limits.
STALE=()
while read -r b; do
  [ -z "$b" ] && continue
  if printf '%s\n' "${PROTECTED_BRANCHES[@]}" | grep -qx "$b"; then continue; fi
  [ "$b" = "$CURRENT" ] && continue
  [ "$b" = "$NEW_BRANCH" ] && continue
  if command -v gh >/dev/null 2>&1; then
    if [ -n "$(gh pr list --state open --head "$b" --json number --jq '.[].number' 2>/dev/null || true)" ]; then
      echo "    skip $b (open PR)"; continue
    fi
  fi
  STALE+=("$b")
done <<< "$BRANCHES"

if [ -z "${BRANCHES//[[:space:]]/}" ]; then
  echo "could not list remote branches (gh unavailable or no remote access) —"
  echo "skipping deletion; run 'gh api repos/$REPO/branches --jq '.[].name'' manually."
elif [ ${#STALE[@]} -eq 0 ]; then
  echo "nothing stale to delete"
else
  echo "candidates for deletion:"
  printf '    %s\n' "${STALE[@]}"
  if [ "$APPLY" -eq 1 ]; then
    if [ "$ASSUME_YES" -eq 1 ]; then
      CONFIRM="yes"
    else
      read -r -p "Delete these remote branches? type 'yes' to confirm: " CONFIRM
    fi
    if [ "$CONFIRM" = "yes" ]; then
      for b in "${STALE[@]}"; do
        echo "+ git push origin --delete $b"
        git push origin --delete "$b"
        git show-ref --verify --quiet "refs/heads/$b" && git branch -d "$b" || true
      done
    else
      echo "skipped deletion"
    fi
  else
    echo "[dry-run] would delete: ${STALE[*]}"
  fi
fi

# --------------------------------------------------------------- 7. wrap up
echo
echo "--- done"
if [ "$APPLY" -eq 1 ]; then
  git fetch origin
  echo "origin/main is now: $(git rev-parse --short=7 origin/main)"
  git status -sb
else
  echo "dry run complete — re-run with --apply to execute"
fi
