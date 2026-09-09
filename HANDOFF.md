# Agent handoff — merge to `main` and clean up branches

Read this first if you are an AI agent picking up this repository. Everything
below was verified against the repo on **2026-09-10**; re-verify with the
commands given rather than trusting the numbers blindly.

**Goal:** land the unpushed work onto `main`, then delete the branches that are
no longer needed.

---

## 1. Why this file exists

The previous coding session ended the moment its pull request (#10) was merged,
which revoked that session's GitHub access. Its last two commits were therefore
**committed locally but never pushed**, and no branch could be created or deleted
while it was locked to its working branch.

So: the merge is *prepared* locally. Your job is to verify it, push it, and clean
up.

## 2. The work being landed

Two local commits sitting on top of `f682f28`:

| Commit | What it is |
| --- | --- |
| `6175011` | Custom-data loader (CSV/TSV/JSON/JSONL/XLSX from `data/`) + the **Import Data** screen at `/import` and its upload/delete endpoints. |
| `2fd92b7` | **Supabase persistence**: imports are upserted into `public.observations` on `observation_id`, so re-uploading the same rows updates them instead of duplicating. Adds `backend/app/persist.py`, `GET /api/data/database`, `POST /api/data/persist`. |

`data/newfare2.csv` (the user's own dataset, 1,169 rows) is tracked on purpose —
do not untrack or delete it.

Regression baseline at `2fd92b7`: backend **186 passed / 4 skipped**, `tsc`
clean, frontend **28 passed**.

## 3. State snapshot (verify, don't trust)

```
local main                    = 1c94805  Merge arena/01a08641-sih26056 into main
                                         parents: ad0c9a2 + 2fd92b7  (real merge)
local arena/01a08641-sih26056 = 513dbbb  = 2fd92b7 + 32a83d9 + 513dbbb
origin/main (last known)      = ad0c9a2  "Merge pull request #10 …"
working tree                  = clean
```

`main` already contains **all of the functional work** (`2fd92b7`). The branch is
two commits ahead only because of this handoff doc and the cleanup script
(`32a83d9`, `513dbbb`) — merge them in or leave them out, the code is fine
either way. `ad0c9a2` is an ancestor of `main`, so `git push origin main` is a
**fast-forward**.

⚠️ The sandbox clone is **shallow** (`.git/shallow` lists `ad0c9a2` and
`f682f28`). Local listings may claim `f682f28` is missing from `origin/main`; it
is not — that commit is already on the remote and the gap is a graft artefact.
Run `git fetch --unshallow origin` (or at least `git fetch origin main`) before
trusting any "ahead/behind" count.

## 4. Rules — do not break these

1. **Never `push --force`.** If a push is rejected, the remote moved: fetch,
   merge/rebase, then push again.
2. **Never delete `main`**, and never delete the branch you are standing on.
3. **Never delete a branch that has an open PR.** Check with
   `gh pr list --state open --head <branch>` first.
4. **Confirm a fast-forward before pushing** — see step 2 below.
5. **List remote branches before deleting any**, and delete only what the user
   agrees is stale. When unsure, ask.
6. Do not "clean up" with `git clean`, `git reset --hard`, or `git checkout .` —
   the user's dataset and uncommitted work must survive.

## 5. Steps

### Step 0 — orient

```bash
git status --short            # must be empty; if not, stop and ask
git branch -vv
git log --oneline --graph --decorate -6
```

### Step 1 — refresh remote refs

```bash
git fetch --unshallow origin 2>/dev/null || git fetch origin
git rev-parse --short=7 origin/main
```

If `origin/main` is **not** `ad0c9a2` any more, the remote moved since the
snapshot: re-check the fast-forward in step 2 and, if it fails, merge
`origin/main` into `main` (`git checkout main && git merge origin/main`) before
pushing. Do not force.

### Step 2 — confirm this is a fast-forward (mandatory)

```bash
git merge-base --is-ancestor origin/main main && echo "SAFE: fast-forward" || echo "STOP: not a fast-forward"
```

Only continue on `SAFE`.

### Step 3 — (only if `main` is *not* already at/after `2fd92b7`) redo the merge

Skip this if `git branch --contains 2fd92b7` already lists `main`, which it does
in the current snapshot.

```bash
git checkout main
git merge --no-ff arena/01a08641-sih26056 -m "Merge arena/01a08641-sih26056 into main: persist imported data to the database"
```

Because this clone is shallow, a plain `git merge` may complain about unrelated
histories. If it does, build the merge commit directly — the branch tree is a
verified strict superset of `main`'s, so taking the branch content is lossless:

```bash
TREE=$(git rev-parse arena/01a08641-sih26056^{tree})
NEW=$(git commit-tree "$TREE" -p "$(git rev-parse main)" -p "$(git rev-parse arena/01a08641-sih26056)" \
      -m "Merge arena/01a08641-sih26056 into main: persist imported data to the database")
git update-ref refs/heads/main "$NEW"
```

### Step 4 — the working branch the user asked for

```bash
git checkout main
git checkout -b feature/supabase-import     # optional; main is already correct
```

Do this **before** pushing if the user wants the work kept on a named branch.

### Step 5 — push

```bash
git push origin main
```

Expected: `ad0c9a2..1c94805  main -> main` with no `rejected` and no `--force`.

### Step 6 — branch cleanup

```bash
# What exists on the remote?
gh api repos/7amankrishna/SIH26056/branches --jq '.[].name'

# Is anything still open? (never delete these)
gh pr list --state open

# Delete one (repeat per stale branch, after confirming with the user)
git push origin --delete <branch>

# Local mirrors of what you deleted
git branch -d <branch>
```

Known stale candidate: **`arena/01a08641-sih26056`** — merged into `main` via PR
#10 and again by the merge above; safe to delete once `main` is pushed and
`feature/supabase-import` (if created) is up to date.

### Step 7 — verify and report

```bash
git fetch origin
git log --oneline -3 origin/main      # 1c94805 (or your merge) must be on top
git status -sb                        # branch should not be "ahead"
gh pr list --state open
gh api repos/7amankrishna/SIH26056/branches --jq '.[].name'
```

Report to the user: the commit now at the tip of remote `main`, which branches
were deleted, and anything deliberately left alone.

## 6. Troubleshooting

| Symptom | Fix |
| --- | --- |
| `! [rejected] main -> main (fetch first)` | Remote moved: `git fetch origin && git merge origin/main`, then push. Never force. |
| `shallow update not allowed` | `git fetch --unshallow origin`, then push. |
| `refusing to delete the current branch` | `git checkout main` first. |
| `gh: auth / permission` errors | Tell the user their GitHub connection in Arena needs reconnecting — do not ask them for tokens or passwords. |
| Merge shows unrelated histories | Use the `commit-tree` recipe in step 3. |
| Tests must be re-run | Backend: `.venv/bin/python -m pytest -q` in `backend/` (expect 186 passed, 4 skipped). Frontend: `npx tsc --noEmit && npx vitest run` in `frontend/` (expect 28 passed). Recreate the venv/node_modules first if the sandbox dropped them. |

## 7. One-shot script

`scripts/land-on-main.sh` implements steps 0–6 with the safety checks built in
and a confirmation prompt before anything destructive. It is dry-run by default;
read it before running it.
