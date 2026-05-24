# Interactive GitHub Upload Guide — Do This Now

Follow this guide step-by-step **exactly as written**. Open PowerShell and run the commands one at a time.

**Estimated time:** 10–15 minutes (including waiting for initial git commands).

---

## What is Git? (60-second explainer)

Git is software that:
- Records every change you make to your code (like save points)
- Lets you work with others on the same project
- Lets you undo mistakes by reverting to earlier versions
- Works with GitHub, which stores your code on the internet

**Today's workflow:**
1. **Local Git repo** (on your computer) — saves snapshots of your code
2. **GitHub** (internet) — stores your code safely and lets you share it
3. **Railway** (later) — deploys your app from GitHub

---

## Step 1: Verify Git is installed

### Open PowerShell

- Press `Windows + R`, type `powershell`, press Enter
- Or search "PowerShell" in Start menu and click it

### Check Git version

Type this command and press Enter:

```powershell
git --version
```

**Expected output:**
```
git version 2.45.0.windows.1
```

(The version number may differ slightly.)

**If you see:**
```
git : The term 'git' is not recognized as the name of a cmdlet, function, script file, or operable program.
```

**FIX:** Git is not installed.
1. Download from: https://git-scm.com/download/win
2. Run the installer (accept defaults).
3. **Restart your computer** (important!).
4. Open a new PowerShell.
5. Try `git --version` again.

**Stop here until you see the git version.** ✓

---

## Step 2: Navigate to your project folder

Type this command exactly and press Enter:

```powershell
cd 'F:\Trading AI 2'
```

### Verify you're in the right place

Type:

```powershell
pwd
```

**Expected output:**
```
F:\Trading AI 2
```

If you see a different path, re-run the `cd` command above.

**Verify the init script exists:**

```powershell
ls -Name init_repo.ps1
```

**Expected output:**
```
init_repo.ps1
```

If you see "Cannot find file," the script wasn't created. Let me know.

✓ **Stop here. You should be in `F:\Trading AI 2` and see `init_repo.ps1`.**

---

## Step 3: Run the initialization script

This script will:
- Check Git is working
- Preview files to be uploaded
- Warn you about dangerous files (secrets, databases)
- Create your first commit
- Ask for your GitHub details
- Set up the remote repository

### Run the script

Type this command and press Enter:

```powershell
powershell -ExecutionPolicy Bypass -File .\init_repo.ps1
```

**What happens:**
- You'll see colorful output from the script
- It will ask you several questions (don't worry, I'll explain each one)
- **The script will NOT push to GitHub** — you control when that happens

---

## Step 4: Answer the script prompts

### Prompt 1: "Would you like to run tests before committing? (recommended) (y/N)"

**What this means:** The script can run automated tests to verify your code works before uploading.

**Your answer:** Type `y` and press Enter

**Expected output:**
```
Running: py -3.14 -m pytest -q
... (test results)
```

If tests pass, you'll see:
```
======== 49 passed in X.XXs ========
```

✓ **Great! Tests are passing.**

If tests fail:
```
FAILED tests/... - ...
```

**What to do:** 
- You can answer `y` to continue anyway (tests aren't required for first push)
- Or `n` to abort and fix tests later

**For now:** If tests fail, answer `y` (continue anyway). We can fix them later.

---

### Prompt 2: "Commit message [default]"

**What this means:** Every commit needs a short message describing what changed.

**Your answer:** Press Enter (accept the default message)

**Default message:** `chore: initial project scaffolding (README, LICENSE, .gitignore, docs)`

(Or type your own message if you want, but keep it short.)

---

### Prompt 3: "GitHub username or org (leave blank to skip setting remote)"

**What this means:** Your GitHub account name (the username you use to log in at github.com).

**Your answer:** Type your GitHub username and press Enter

**Examples:**
- `john-trader`
- `eth-ai-developer`
- `trading-bot-master`

**Don't have a GitHub account?** Create one free at https://github.com/signup

---

### Prompt 4: "Repository name (will be created on GitHub if missing)"

**What this means:** The name of your repository on GitHub.

**Your answer:** Type a repository name and press Enter

**Good names:**
- `eth-futures-ai` ✓ (simple, lowercase, hyphens)
- `trading-ai-framework` ✓
- `eth-optimizer` ✓

**Bad names:**
- `ETH Futures AI` ✗ (spaces and uppercase)
- `eth_futures_ai` ✗ (underscores)

**What it becomes:** `https://github.com/your-username/eth-futures-ai`

---

### Prompt 5: "Protocol to use for remote: HTTPS or SSH? (h/s) [h]"

**What this means:** How to connect to GitHub (HTTPS = easier, SSH = more secure but harder).

**Your answer:** Type `h` and press Enter (HTTPS is beginner-friendly)

**Explanation:**
- **HTTPS** (h) — Uses your GitHub username + password/token. Easier.
- **SSH** (s) — Uses a cryptographic key. More advanced.

For beginners: **HTTPS** is fine. ✓

---

## Step 5: Review script output

After answering the prompts, the script will show you:

### Staged files summary

You'll see a list of files like:
```
.gitignore
README.md
LICENSE
docs/
backtester/
optimizer/
...
```

**Check:** Do you see `.env`, `.sqlite`, or `.db` files? 

**If YES:** ❌ STOP and tell me — we need to remove them before pushing.

**If NO:** ✓ Continue.

### Ignored files sample

You'll see files like:
```
.venv/
__pycache__/
memory/
*.sqlite
.env
```

**What this means:** These files will NOT be uploaded (good — they're secrets and runtime data).

### Final message

```
Repository initialized locally.
Remote configured: https://github.com/your-username/eth-futures-ai.git

When you are ready to publish to GitHub, run:
    git push -u origin main
```

**✓ Excellent! The script is done.**

---

## Step 6: Create empty GitHub repository

Now you'll create a repository on GitHub to receive your code.

### Go to GitHub

1. Open your browser
2. Go to https://github.com/new
3. Log in with your GitHub account (if not already logged in)

### Fill in the form

**Repository name field:**
- Type the name you answered in Prompt 4 (e.g., `eth-futures-ai`)

**Description field (optional):**
- Type: `ETH Futures AI trading framework with TradingView webhook support`

**Public or Private:**
- **Public** = anyone can see your code (good for open-source projects)
- **Private** = only you can access it

- Choose based on your preference. Both work fine.

### IMPORTANT: Do NOT initialize with files

You'll see three checkboxes:
- [ ] Add a README file
- [ ] Add a .gitignore
- [ ] Choose a license

**✗ DO NOT check any of these boxes.**

**Why?** Your local repository already has these files. If you initialize GitHub with them too, Git will be confused about which version is correct. The script will handle merging correctly.

### Create the repository

Click the green **"Create repository"** button.

### You'll see a page like:

```
…or push an existing repository from the command line

git remote add origin https://github.com/your-username/eth-futures-ai.git
git branch -M main
git push -u origin main
```

**Don't worry about this** — the init script already configured most of it. Keep this page open for reference.

---

## Step 7: Push to GitHub

Back in PowerShell (you should still be in `F:\Trading AI 2`), type this command and press Enter:

```powershell
git push -u origin main
```

### What this does:
- `git push` = upload your commits to GitHub
- `-u origin main` = set GitHub's `main` as your default branch

### You may be asked for credentials

**First time:** GitHub may ask:

```
Username for 'https://github.com': 
```

Type your GitHub username and press Enter.

```
Password for 'https://github.com/your-username': 
```

**Important:** Do NOT type your GitHub password!

Instead:
1. Create a **Personal Access Token (PAT)** at: https://github.com/settings/tokens
2. Click **"Generate new token (classic)"**
3. Name it something like "GitHub Upload"
4. Check the box `repo` (full control of private repositories)
5. Click **"Generate token"**
6. Copy the token (it looks like `ghp_xxxxxxxxxxxxxxxxxxxxxxxxxxxx`)
7. Paste it as the password

(If you already set up Git credentials on your computer, it may not ask.)

### Expected output after push:

```
Enumerating objects: 150, done.
Counting objects: 100% (150/150), done.
Delta compression using up to 8 threads
Compressing objects: 100% done.
Writing objects: 100% done.
remote: Resolving deltas: 100% done.
To https://github.com/your-username/eth-futures-ai.git
 * [new branch]      main -> main
Branch 'main' set up to track remote branch 'main' from 'origin'.
```

**✓ Success!** Your code is now on GitHub.

---

## Step 8: Verify upload (in browser)

### Go to your GitHub repository

Open this URL (replace with your username and repo name):

```
https://github.com/your-username/eth-futures-ai
```

### You should see:

**Top of the page:**
- Repository name: `eth-futures-ai`
- Branch dropdown showing: `main`
- Files listed:
  - `.github/`
  - `.gitignore`
  - `backtester/`
  - `README.md` ← **important: should be visible**
  - `LICENSE` ← **important: should be visible**
  - `docs/`
  - etc.

**Scroll down to see:**
- README.md content displayed (your project description)

**Check the commit message:**
- Look for a commit listing (usually shows "chore: initial project..." or your custom message)

**✓ If you see all of this, the upload worked!**

---

## Step 9: Verify NO secrets were uploaded

### Search GitHub for dangerous files

1. In your GitHub repository, press `Ctrl + K` (or click the search icon at top)
2. Search for: `.env`
3. You should see: "No results"

**Repeat search for:**
- `secrets`
- `password`
- `key`
- `.sqlite`

All should return "No results." ✓

---

## Step 10: Verify locally

Back in PowerShell, verify the local Git state:

```powershell
git log --oneline
```

You should see:

```
abc1234 (HEAD -> main, origin/main) chore: initial project scaffolding
```

**Explanation:**
- `HEAD -> main` = you're on the local `main` branch
- `origin/main` = the GitHub `main` branch is synced
- The commit message is shown

**If you see `origin/main`**, you're synced with GitHub. ✓

---

## Git Concepts Explained (simple)

### `git init`
Creates a `.git` folder on your computer. This folder stores all the history and snapshots of your project.

**Analogy:** Like opening a new notebook to start journaling.

### `commit`
Takes a snapshot of your code at a moment in time. Every commit has a message describing what changed.

**Analogy:** Like a save point in a video game.

### `branch`
A version of your code. `main` is the default branch (the "production" version).

**Analogy:** Like a separate copy of your project where you can experiment without affecting the main version.

### `main`
The name of your default branch. It's where stable, tested code lives.

**Analogy:** Like the "official version" of your project.

### `remote`
A link to a repository on the internet (GitHub, GitLab, etc.).

**Analogy:** Like a cloud backup service — your code is saved both locally and on the internet.

### `origin`
The name of your remote. `origin` usually means GitHub (your primary remote).

**Analogy:** Like naming your cloud backup "my-backup."

### `git push`
Uploads your local commits to the remote (GitHub).

**Analogy:** Like uploading a file to the cloud drive.

### `git push -u origin main`
- `git push` = upload
- `-u` = "set as default" (future pushes won't need `-u`)
- `origin main` = to the GitHub `main` branch

---

## Troubleshooting Common Issues

### Problem: "git is not recognized"

**Cause:** Git not installed or not on PATH.

**Fix:**
1. Install Git: https://git-scm.com/download/win
2. Choose "Use Git from the command line"
3. Restart your computer
4. Open new PowerShell and try again

---

### Problem: "The execution policy of this user is not set to 'RemoteSigned'"

**Cause:** PowerShell won't run local scripts by default.

**Fix:** Use the bypass flag (we already did this):

```powershell
powershell -ExecutionPolicy Bypass -File .\init_repo.ps1
```

---

### Problem: "fatal: remote origin already exists"

**Cause:** A GitHub remote is already configured (maybe from a previous attempt).

**Fix:** The script asks if you want to replace it. Answer `y` (yes).

---

### Problem: "fatal: remote 'origin' does not appear to be a 'git' repository"

**Cause:** The remote URL is malformed or missing.

**Fix:** Verify and fix the remote:

```powershell
git remote -v
```

You should see:

```
origin  https://github.com/your-username/eth-futures-ai.git (fetch)
origin  https://github.com/your-username/eth-futures-ai.git (push)
```

If URL is wrong, fix it:

```powershell
git remote set-url origin https://github.com/your-username/eth-futures-ai.git
```

---

### Problem: "fatal: 'origin' does not appear to be a 'git' repository"

**Cause:** Same as above.

**Fix:** Check and correct the remote URL as shown above.

---

### Problem: "fatal: repository not found" or "Invalid username/password"

**Cause:** Wrong credentials or GitHub repo doesn't exist.

**Fix:**
1. Verify your GitHub username is correct: `git remote -v`
2. If using HTTPS, use a Personal Access Token (PAT), not your GitHub password:
   - Create PAT: https://github.com/settings/tokens
   - Use as password when prompted
3. Ensure the repository exists on GitHub (check https://github.com/your-username)

---

### Problem: "Permission denied (publickey)"

**Cause:** You chose SSH but SSH keys aren't set up.

**Fix:**
1. Use HTTPS instead (answer `h` when prompted)
2. Or set up SSH keys: https://docs.github.com/en/authentication/connecting-to-github-with-ssh

---

### Problem: "Everything up-to-date" (but nothing uploaded)

**Cause:** No changes to push or already synced.

**Fix:**
1. Verify files were staged: `git status --short`
2. If nothing shows, re-run the init script
3. Try push again: `git push -u origin main`

---

### Problem: "Please tell me who you are" when running init script

**Cause:** Git doesn't know your name and email.

**Fix:** Configure Git (one-time):

```powershell
git config --global user.name "Your Name"
git config --global user.email "your-email@example.com"
```

Then re-run the init script.

---

## Final Checklist: After GitHub Upload

- [ ] Git installed and working (`git --version` shows version)
- [ ] In project folder (`F:\Trading AI 2`)
- [ ] Ran init script successfully
- [ ] All tests passed (or skipped)
- [ ] GitHub repo created (empty, no README/license initialization)
- [ ] `git push -u origin main` succeeded
- [ ] GitHub page shows files (README.md, LICENSE, docs/, etc.)
- [ ] Searched GitHub for `.env`, `secrets`, `password`, `.sqlite` — all returned no results
- [ ] No `.env` or secrets visible in GitHub files
- [ ] `git log --oneline` shows `origin/main` (local and GitHub synced)
- [ ] Remote URL is correct: `git remote -v`

---

## What Success Looks Like

### In PowerShell:

```powershell
PS F:\Trading AI 2> git log --oneline
abc1234 (HEAD -> main, origin/main) chore: initial project scaffolding (README, LICENSE, .gitignore, docs)

PS F:\Trading AI 2> git remote -v
origin  https://github.com/your-username/eth-futures-ai.git (fetch)
origin  https://github.com/your-username/eth-futures-ai.git (push)

PS F:\Trading AI 2>
```

### In GitHub browser:

- Repository name: `eth-futures-ai`
- Branch: `main`
- Files visible: `.gitignore`, `README.md`, `LICENSE`, `backtester/`, `optimizer/`, `webhook/`, etc.
- No `.env`, `.sqlite`, or secrets in file listing
- README.md content visible (project description)
- Commit history shows your commit

---

## Ready for Next Steps

After GitHub upload is confirmed:

### 1. Railway Deployment
- See `docs/RAILWAY_DEPLOY.md`
- Link your GitHub repo to Railway
- Railway auto-deploys on push

### 2. TradingView Webhook Integration
- See `docs/TRADINGVIEW_ALERTS.md`
- Get your Railway webhook URL
- Add TradingView alert with webhook

### 3. Android Phone Paper Trading
- See `docs/MOBILE_WORKFLOW.md`
- Forward test on ETH Futures from your phone
- TradingView app sends alerts → Railway webhook → Paper trading engine

---

## Next: Run the script now!

In PowerShell:

```powershell
cd 'F:\Trading AI 2'
powershell -ExecutionPolicy Bypass -File .\init_repo.ps1
```

Answer the prompts following the guide above. When done, let me know the results and any questions!

