# Pre-push Checklist (what to verify before pushing to GitHub)

- [ ] .gitignore includes `.env`, database files, `state/`, and `memory/` artifacts
- [ ] No `.env` or secret files staged: `git status --porcelain`
- [ ] Run tests: `py -3.14 -m pytest -q` (all tests passing)
- [ ] Linting / formatting applied where necessary
- [ ] README updated with accurate instructions
- [ ] LICENSE added and correct
- [ ] Sensitive files removed from history if accidentally committed (use `git rm --cached <file>` and `git commit`)
- [ ] CI configured (.github/workflows/ci.yml present)
- [ ] Dockerfile and Procfile present for deployment

When ready, push:

```bash
git add .
git commit -m "chore: prepare repo for initial push"
git push -u origin main
```
