# Quick Reference Card — Keep This Open While Running the Script

## Commands to run (copy-paste one at a time)

### 1. Verify Git installed
```powershell
git --version
```
**Expect:** `git version 2.XX.X.windows.X`

---

### 2. Go to project folder
```powershell
cd 'F:\Trading AI 2'
```

### 3. Verify you're there
```powershell
pwd
```
**Expect:** `F:\Trading AI 2`

---

### 4. Run the init script
```powershell
powershell -ExecutionPolicy Bypass -File .\init_repo.ps1
```

---

## Script Prompts — Quick Answers

| Prompt | Your Answer | Why |
|--------|-------------|-----|
| "Run tests?" | `y` | Ensures code works before upload |
| "Commit message?" | Press Enter | Accept default: `chore: initial project...` |
| "GitHub username?" | Your username | E.g., `john-trader` |
| "Repository name?" | Lowercase, hyphens | E.g., `eth-futures-ai` |
| "HTTPS or SSH?" | `h` | HTTPS is beginner-friendly |

---

## After Script: GitHub Setup

### 1. Go to GitHub
```
https://github.com/new
```

### 2. Fill form
- **Repository name:** Match your answer from prompt 4
- **Description:** "ETH Futures AI trading framework with TradingView webhook support"
- **Public/Private:** Your choice
- **✗ DO NOT check** "Initialize with README/license/gitignore"

### 3. Click "Create repository"

---

## After GitHub Repo Created: Push to GitHub

```powershell
git push -u origin main
```

**When asked for password:**
- Get Personal Access Token: https://github.com/settings/tokens
- Click "Generate new token (classic)"
- Check `repo` box
- Generate and copy token
- Paste as password

---

## Verify Success (in Browser)

Go to: `https://github.com/your-username/your-repo-name`

**Verify you see:**
- [ ] Files: `.gitignore`, `README.md`, `LICENSE`, `docs/`, `backtester/`, etc.
- [ ] Branch: `main` (top-left dropdown)
- [ ] README.md content (scroll down)
- [ ] No `.env` or `.sqlite` files

**Search for dangerous files:**
- Search `.env` → No results ✓
- Search `secrets` → No results ✓
- Search `password` → No results ✓

---

## Verify Locally (in PowerShell)

```powershell
git log --oneline
```

**Expect:** `abc1234 (HEAD -> main, origin/main) chore: initial project...`

**Key signs of success:**
- `origin/main` shows (local and GitHub synced)
- Your commit message is there

---

## Common Errors Quick Fixes

| Error | Fix |
|-------|-----|
| "git is not recognized" | Install Git from https://git-scm.com/download/win, restart |
| "execution policy not set" | Already using bypass flag in step 4 — should work |
| "remote origin already exists" | Script asks to replace — answer `y` |
| "invalid username/password" | Use Personal Access Token, not password |
| "permission denied (publickey)" | Use HTTPS (`h`), not SSH |
| "repository not found" | Verify GitHub username and repo name are correct |

---

## What Happens Next

After confirmed upload:

1. **Railway Deployment** (15 min)
   - Link GitHub to Railway
   - Configure env variables
   - Deploy

2. **TradingView Webhook** (10 min)
   - Get webhook URL from Railway
   - Add TradingView alert
   - Start paper trading

3. **Android Mobile Testing** (ongoing)
   - TradingView app on phone
   - Send alerts → Railway webhook → Paper trading
   - Monitor fills and P&L from phone

