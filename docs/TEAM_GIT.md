# Team git workflow (hackathon day)

Two people, two computers, one repo: `github.com/jackylee0503/hp-ready`.

## Structure

```
main              ← must always run: streamlit run app.py
├── junwoo/loader ← Junwoo: schema.py, loader.py, extract.py, app.py
└── engine        ← potatohater8: engine.py, calibrate.py
```

## Once, at the start

1. Accept the collaborator invite: https://github.com/jackylee0503/hp-ready/invitations (without it you cannot push).
2. `schema.py` is already on `main`. It is the contract for both of us (`House` in, `Result` out).
3. Engine owner: push a stub `engine.py` to `main` first, with `evaluate(h, p=DEFAULT, n=500, seed=0) -> Result` returning a valid default `Result`. The app runs without it, but the stub lets the UI show real fields early.
4. Create your branch:

```bash
git switch main && git pull
git switch -c engine            # Junwoo: git switch -c junwoo/loader
```

## While working (repeat)

```bash
git add engine.py                       # only your own files, never git add -A
git commit -m "engine: radiator output step"
git push -u origin engine               # -u only the first time, then just git push
```

Commit small and often: every time something works.

## Merging into main (every 1-2 hours)

```bash
git switch engine
git pull origin main          # take what the other person merged first
python engine.py              # check everything runs on your branch
git switch main && git pull
git merge engine
git push
```

Then tell the other person: "merged into main, please pull". A GitHub PR works too, but there is no time to wait for reviews today; a direct merge is fine. We never edit the same files, so conflicts should be rare.

## Two rules

1. **`schema.py` changes go straight to `main`** (the one exception). Left on a branch, the other person keeps coding against the old contract. Change it, push to `main`, tell the other person. Only Junwoo edits `schema.py`; ask him for a new field.
2. **Don't touch the other person's files.** If you see a bug in someone else's file, tell them instead of fixing it.

## Worktrees

Not needed between us (different computers). Only if one person wants two Claude sessions at once (e.g. loader and app in parallel), because two sessions in one folder overwrite each other's files:

```bash
git worktree add ../hp-ready-app -b junwoo/app
# start the second session in ../hp-ready-app
```

## Cheat sheet

| Want to | Command |
| --- | --- |
| See where I am | `git status` |
| Get the latest main into my branch | `git pull origin main` |
| Save my work | `git add <my files>` then `git commit -m "..."` then `git push` |
| Undo uncommitted changes to one file | `git restore <file>` |
| Something is weird | stop and ask before any `reset` or `--force` |
