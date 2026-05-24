# Git & GitHub Quick Guide (Beginner Friendly)

This guide shows the exact commands you'll run to initialize Git, make your first commit, and push to GitHub. Explanations follow each command.

1) Initialize a new Git repository (run once per project):

```bash
git init
```
- Creates a new `.git` folder and starts tracking changes locally.

2) Stage changes to be committed:

```bash
git add .
```
- `git add .` stages all new/modified files in the current directory (except those ignored by `.gitignore`).

3) Create your first commit:

```bash
git commit -m "chore: initial project files (README, LICENSE, .gitignore)"
```
- Commits the staged snapshot with a short message. Use a conventional prefix (`feat`, `fix`, `chore`, `docs`).

4) Rename the default branch to `main` (modern default):

```bash
git branch -M main
```

5) Add the remote GitHub repository (replace URL with your repo):

```bash
git remote add origin https://github.com/<your-username>/<your-repo>.git
```

6) Push the `main` branch to GitHub and set upstream:

```bash
git push -u origin main
```

Branching recommendations
- `feature/<short-description>` — new features
- `fix/<short-description>` — bug fixes
- `hotfix/<short-description>` — urgent production fixes
- `chore/<task>` — housekeeping (docs, deps)

Commit message recommendations
- Use `type(scope): short description` format
- Keep subject <= 72 chars; optionally add a body separated by a blank line
- Examples:
  - `feat(backtester): add position sizing by risk percent`
  - `fix(engine): handle numpy.datetime64 timestamps`

Tagging and releases
- Use annotated tags for releases:

```bash
git tag -a v1.0.0 -m "v1.0.0 release"
git push origin v1.0.0
```

Notes
- Add your GitHub repo URL in step 5. If you prefer SSH, use the SSH URL.
- Never commit `.env` or secrets; add them to `.gitignore` and use Railway/GitHub Secrets.
