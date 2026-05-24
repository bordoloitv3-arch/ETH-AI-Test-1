# GitHub Setup Guide — Beginner Walkthrough

This guide walks you through installing Git, running the initialization script, creating a GitHub repository, and safely pushing your ETH Futures AI project to GitHub.

**Estimated time:** 15-20 minutes.

---

## Step 1: Install Git on Windows

### What is Git?
Git is software that tracks changes to your code over time. Think of it like a "save system" for your entire project — every commit is like a save point with a description of what changed.

### Installation steps

1. **Download Git for Windows:**
   - Visit: https://git-scm.com/download/win
   - The website should auto-detect Windows and show a download button.
   - Click the download button (it will download `Git-X.XX.X-64-bit.exe`).

2. **Run the installer:**
   - Open the downloaded `.exe` file.
   - You'll see a setup wizard. Click **Next** through the dialogs.
   - **Important step:** When asked "Adjusting your PATH environment," select:
     - **"Use Git from the command line and also from 3rd-party software"** (default, recommended).
   - Keep all other defaults. Click **Install**.
   - At the end, click **Finish** (you can uncheck "View Release Notes").

3. **Verify Git installed correctly:**
   - Open a **new PowerShell window** (close and reopen).
   - Type this command and press Enter:

```powershell
git --version
```

   - You should see output like: `git version 2.45.0.windows.1`
   - If you see "git is not recognized," your PATH wasn't updated. Try:
     - Restarting your computer, or
     - Reinstalling Git and choosing "Use Git from the command line."

---

## Step 2: Navigate to your project folder

**What this does:** Tells PowerShell where your project is located so we can run commands in the right place.

1. Open **PowerShell** (right-click on the desktop or start menu, search "PowerShell").
2. Type this command and press Enter:

```powershell
cd 'F:\Trading AI 2'
```

3. Verify you're in the right folder by typing:

```powershell
pwd
```

   - You should see: `F:\Trading AI 2` (or the path your system shows).
   - If you see a different path, type the `cd` command again.

---

## Step 3: Verify required files exist

Before running the initialization script, let's confirm the necessary files are present.

Run these commands one at a time:

```powershell
# Check for .gitignore (tells Git which files to NOT track)
ls -Name .gitignore

# Check for README.md (project description)
ls -Name README.md

# Check for LICENSE (open-source license)
ls -Name LICENSE

# Check for the initialization script
ls -Name init_repo.ps1
```

**Expected output:**
```
.gitignore
README.md
LICENSE
init_repo.ps1
```

If any file is missing, let me know before continuing.

---

## Step 4: Run the initialization script

The `init_repo.ps1` script automates Git initialization with safety checks.

### Allow the script to run (if needed)

PowerShell may block local scripts for security. Run this command to bypass the policy temporarily for this script:

```powershell
powershell -ExecutionPolicy Bypass -File .\init_repo.ps1
```

### What happens when you run the script

The script will:
1. Check if Git is installed ✓
2. Preview files that would be staged
3. **Warn you if sensitive files are detected** (`.env`, `.sqlite`, etc.)
4. Optionally run tests (`py -3.14 -m pytest -q`)
5. Stage files with `git add .`
6. Show you staged files and ignored files
7. Create your first commit
8. Rename the branch to `main`
9. Ask for your GitHub username and repository name
10. Configure the remote repository
11. Show you the exact `git push` command to run

### Running the script

Type this command and press Enter:

```powershell
powershell -ExecutionPolicy Bypass -File .\init_repo.ps1
```

The script will start asking questions. Here's how to answer them:

---

## Step 5: Answer script prompts

### Prompt 1: "Would you like to run tests before committing? (recommended) (y/N)"

**Answer:** `y` (yes) — this ensures your code works before committing.

Output will show test results. If all tests pass:
```
======== X passed in X.XXs ========
```

If tests fail, you can:
- Answer `y` to continue anyway (not recommended for first push).
- Answer `n` to abort, fix tests, and re-run the script.

### Prompt 2: "Commit message [default]"

**Answer:** Press Enter to accept the default message:
```
chore: initial project scaffolding (README, LICENSE, .gitignore, docs)
```

Or type your own message if you prefer (keep it short).

### Prompt 3: "GitHub username or org (leave blank to skip setting remote)"

**Answer:** Type your GitHub username (the one you use to log in).

Example: `john-trader`

**Important:** If you don't have a GitHub account yet, create one at https://github.com/signup (free).

### Prompt 4: "Repository name (will be created on GitHub if missing)"

**Answer:** Type a name for your repository. Use lowercase letters, hyphens, no spaces.

Examples:
- `eth-futures-ai`
- `trading-ai-framework`
- `eth-optimizer`

This will become: `https://github.com/your-username/your-repo-name`

### Prompt 5: "Protocol to use for remote: HTTPS or SSH? (h/s) [h]"

**Answer:** `h` (HTTPS, the default) — simpler for beginners.

- HTTPS: easier, uses username/password or token
- SSH: more secure but requires key setup

---

## Step 6: Review script output

After answering the prompts, the script will show:

### Staged files summary
```
.gitignore
README.md
LICENSE
docs/GIT_GUIDE.md
docs/PRE_PUSH_CHECKLIST.md
... (more files)
```

**Verify:** These should look like your project files, NOT `.env` or `.sqlite` files.

### Ignored files sample
```
.venv/
__pycache__/
memory/
... (more files)
```

**What this means:** These files will NOT be tracked by Git (good for secrets and runtime data).

### Final message
```
Repository initialized locally.
Remote configured: https://github.com/your-username/your-repo-name.git

When you are ready to publish to GitHub, run:
    git push -u origin main
```

**✓ If you see this, your local repo is ready.**

---

## Step 7: Safety check — verify no secrets are staged

**Critical step:** Before pushing, we'll verify no dangerous files are included.

Run this command:

```powershell
git status --short
```

**Expected output:** You should see `.gitignore`, `.github/`, `README.md`, etc. — but NO `.env` files or database files.

**If you see dangerous files:**

Example of DANGEROUS files:
```
M .env
M secrets.txt
A my_database.sqlite
```

**Fix:** Run this for each dangerous file:

```powershell
git reset HEAD .env
git reset HEAD secrets.txt
git reset HEAD my_database.sqlite
```

Then add them to `.gitignore` if they should never be tracked:

```powershell
echo ".env" >> .gitignore
echo "*.sqlite" >> .gitignore
```

Then re-stage and re-commit:

```powershell
git add .gitignore
git commit -m "chore: add secrets to .gitignore"
```

---

## Step 8: Create a GitHub repository

Now you'll create an empty repository on GitHub. **Do NOT initialize it with README/LICENSE** because your local repo already has them.

### Create the repo on GitHub

1. Open GitHub in your browser: https://github.com
2. Log in with your account.
3. Click the **"+"** icon in the top-right corner.
4. Select **"New repository"**.
5. Fill in the form:
   - **Repository name:** Use the name you answered in the script (e.g., `eth-futures-ai`).
   - **Description (optional):** "ETH Futures AI trading framework with TradingView webhook support."
   - **Public or Private:** Choose based on your preference.
     - Public = anyone can see and download your code (good for open-source).
     - Private = only you and collaborators can see it.
   - **Do NOT check** "Initialize this repository with" (README, .gitignore, license) — your local repo has these.
6. Click **"Create repository"**.

### Copy the repository URL

After creation, GitHub shows:
```
https://github.com/your-username/eth-futures-ai.git
```

Copy this URL (you may need it for troubleshooting, though the script should have set it already).

---

## Step 9: Push to GitHub

Now you'll upload your local commits to GitHub.

In PowerShell (from your project root), run:

```powershell
git push -u origin main
```

### What this command does:
- `git push` = upload commits to GitHub
- `-u origin main` = set GitHub's `main` branch as the default upstream (so future pushes are simpler)

### What you should see:

**On first push with HTTPS,** GitHub may ask for credentials:
```
Username for 'https://github.com': your-username
Password for 'https://github.com/your-username': ***
```

- **Username:** Your GitHub username.
- **Password:** NOT your GitHub password! Instead:
  - Create a **Personal Access Token (PAT)** at https://github.com/settings/tokens
  - Use the token as the password.

**Or:** If you set up two-factor authentication, you MUST use a PAT (not your password).

### After successful push:

Output will show:
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

## Step 10: Verify the upload

### Check GitHub in the browser

1. Go to https://github.com/your-username/your-repo-name
2. You should see:
   - **Files:** Your project files (.gitignore, README.md, LICENSE, docs/, backtester/, optimizer/, etc.)
   - **Branch:** "main" (shown at the top-left)
   - **Commit message:** "chore: initial project scaffolding..." (or your custom message)

### Verify locally

Run:

```powershell
git log --oneline
```

You should see your commit:
```
abc1234 (HEAD -> main, origin/main) chore: initial project scaffolding (README, LICENSE, .gitignore, docs)
```

The `origin/main` indicates your local `main` is synced with GitHub.

### Verify no secrets leaked

On GitHub, use the search bar at the top and search for:
- `.env`
- `secrets`
- `password`

If nothing shows up in files, you're good. ✓

---

## Troubleshooting

### Error: "git is not recognized"

**Cause:** Git is not installed or not on PATH.

**Fix:**
1. Install Git from https://git-scm.com/download/win
2. Choose "Use Git from the command line."
3. **Restart your computer** (important!).
4. Open a new PowerShell and try again.

---

### Error: "The execution policy of this user is not set to 'RemoteSigned'"

**Cause:** PowerShell is blocking your script.

**Fix:** Run the script with the bypass flag:

```powershell
powershell -ExecutionPolicy Bypass -File .\init_repo.ps1
```

Or set the policy once:

```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

---

### Error: "fatal: remote origin already exists"

**Cause:** A remote called "origin" is already configured.

**Fix:**

Option A: Let the script update it (it will ask).

Option B: Remove the old remote manually:

```powershell
git remote remove origin
git remote add origin https://github.com/your-username/your-repo-name.git
```

---

### Error: "Everything up-to-date" during push

**Cause:** Your local and remote branches are already synced (or nothing was staged).

**Fix:**
1. Verify you committed changes: `git status`
2. If you see "nothing to commit," re-run the init script.

---

### Error: "fatal: 'origin' does not appear to be a 'git' repository"

**Cause:** The remote URL is misconfigured.

**Fix:** Check your remote configuration:

```powershell
git remote -v
```

You should see:
```
origin  https://github.com/your-username/your-repo-name.git (fetch)
origin  https://github.com/your-username/your-repo-name.git (push)
```

If the URL is wrong, fix it:

```powershell
git remote set-url origin https://github.com/your-username/correct-repo-name.git
```

---

### Error: "Permission denied (publickey)" (SSH users)

**Cause:** SSH key not set up.

**Fix:**
1. Use HTTPS instead (`h` when prompted by the script).
2. Or set up SSH keys: https://docs.github.com/en/authentication/connecting-to-github-with-ssh

---

### Error: "fatal: repository not found" or "invalid username/password"

**Cause:** Wrong username, password, or repository doesn't exist.

**Fix:**
1. Verify your GitHub username is correct: `git remote -v`
2. If using HTTPS, use a Personal Access Token (PAT) instead of your password:
   - Create one: https://github.com/settings/tokens
   - When prompted for password, paste the PAT.
3. Ensure the repository exists on GitHub (check https://github.com/your-username).

---

### Error: "push rejected — pre-receive hook declined"

**Cause:** Branch protection rules or other GitHub settings.

**Fix:**
1. Check your repository settings on GitHub (Settings > Branches).
2. Disable branch protection temporarily if needed.
3. Try push again.

---

### Error: "refusing to merge unrelated histories"

**Cause:** Your local repo and remote have different histories (both have commits).

**Fix:** This shouldn't happen with the init script, but if it does:

```powershell
git pull --allow-unrelated-histories origin main
git push -u origin main
```

---

## Next Steps: Railway Deployment

Once your repository is on GitHub, you can deploy to Railway:

1. Go to https://railway.app
2. Sign up (free tier available).
3. Create a new project and link your GitHub repository.
4. Configure environment variables (see `.env.example`).
5. Railway will automatically deploy your app.

See `docs/RAILWAY_DEPLOY.md` for detailed Railway setup.

---

## Summary

You're now ready to:
- ✓ Use Git locally
- ✓ Push to GitHub
- ✓ Prepare for Railway deployment

Next: Connect to TradingView, test your webhook, and forward-test with paper trading!

