<#
init_repo.ps1

Beginner-friendly PowerShell script to initialize a Git repository safely,
perform pre-commit safety checks, create the first commit, and configure
the GitHub remote. The script does NOT push automatically — it prints the
exact `git push -u origin main` command for you to run when ready.

Usage: Open PowerShell, cd to the project root (where this file lives),
and run:

    .\init_repo.ps1

The script is intentionally non-destructive and includes multiple safety
prompts to prevent secrets from being committed accidentally.
#>

## ---------------------- Helper functions ----------------------
function Write-Info($msg) { Write-Host $msg -ForegroundColor Cyan }
function Write-Warn($msg) { Write-Host $msg -ForegroundColor Yellow }
function Write-Ok($msg)   { Write-Host $msg -ForegroundColor Green }
function Write-Err($msg)  { Write-Host $msg -ForegroundColor Red }

function Run-Checked($cmd) {
    # Runs an external command and returns @{ Success = $bool; Output = $text }
    try {
        $out = & cmd /c "$cmd" 2>&1
        $success = $LASTEXITCODE -eq 0
        return @{ Success = $success; Output = $out }
    } catch {
        return @{ Success = $false; Output = $_.Exception.Message }
    }
}

## ---------------------- Step 1: Check Git ----------------------
Write-Host "\n=== ETH Futures AI — Git repo initializer ===" -ForegroundColor Magenta

$gitCmd = Get-Command git -ErrorAction SilentlyContinue
if (-not $gitCmd) {
    Write-Err "Git does not appear to be installed or not on PATH."
    Write-Host "Follow these steps to install Git on Windows:" -ForegroundColor Yellow
    Write-Host "  1) Download: https://git-scm.com/download/win" -ForegroundColor Cyan
    Write-Host "  2) Run installer and accept defaults (use Git from the command line)." -ForegroundColor Cyan
    Write-Host "  3) Reopen PowerShell and re-run this script." -ForegroundColor Cyan
    exit 1
}

Write-Ok "Git found: $($gitCmd.Path)"; Start-Sleep -Milliseconds 200

## ---------------------- Step 2: Basic repo file checks ----------------------
Write-Info "\nPreflight checks for essential files..."

$root = Get-Location
$hasGitignore = Test-Path -Path (Join-Path $root '.gitignore')
$hasReadme = Test-Path -Path (Join-Path $root 'README.md')
$hasLicense = Test-Path -Path (Join-Path $root 'LICENSE')

if (-not $hasGitignore) { Write-Warn "Missing .gitignore — we'll continue but please add one." }
else { Write-Ok ".gitignore found." }
if (-not $hasReadme) { Write-Warn "Missing README.md — recommended to add one." }
else { Write-Ok "README.md found." }
if (-not $hasLicense) { Write-Warn "Missing LICENSE — consider adding an open-source license." }
else { Write-Ok "LICENSE found." }

## ---------------------- Step 3: Preview what would be staged ----------------------
Write-Info "\nPreviewing files that would be staged by 'git add .' (dry-run)..."

$dryRun = Run-Checked "git add --dry-run ."
if (-not $dryRun.Success) {
    # git add --dry-run may return non-zero if no files or on older Git versions; fall back to listing
    $dryOut = Run-Checked "git ls-files --others --exclude-standard"
    $dryText = $dryOut.Output
} else {
    $dryText = $dryRun.Output
}

if (-not $dryText) { Write-Info "No unstaged or untracked files detected by dry-run." }
else { Write-Host $dryText }

# Safety pattern checks in the dry-run output (basic checks)
$sensitivePatterns = @('\.env', '\.env\.', '\.sqlite', '\.db', 'secrets', 'credential', 'password', 'KEY', 'token')
$sensitiveHits = @()
foreach ($p in $sensitivePatterns) {
    if ($dryText -match $p) { $sensitiveHits += $Matches[0] }
}

if ($sensitiveHits.Count -gt 0) {
    Write-Warn "Potential sensitive filenames detected in the preview:"; $sensitiveHits | Get-Unique | ForEach-Object { Write-Warn "  $_" }
    $cont = Read-Host "Do you want to continue staging and commit these files? (y/N)"
    if ($cont.ToLower() -ne 'y') { Write-Err "Aborting. Remove or add sensitive files to .gitignore, then re-run the script."; exit 2 }
}

## ---------------------- Step 4: Initialize repository (if needed) ----------------------
if (-not (Test-Path -Path (Join-Path $root '.git'))) {
    Write-Info "\nInitializing a new Git repository..."
    $init = Run-Checked "git init"
    if (-not $init.Success) { Write-Err "git init failed: $($init.Output)"; exit 3 }
    Write-Ok "Repository initialized.";
} else {
    Write-Info "A Git repository already exists in this folder.";
}

## ---------------------- Step 5: Optionally run tests before staging ----------------------
$runTests = Read-Host "Would you like to run tests before committing? (recommended) (y/N)"
if ($runTests.ToLower() -eq 'y') {
    Write-Info "Running: py -3.14 -m pytest -q"
    $testRes = Run-Checked "py -3.14 -m pytest -q"
    Write-Host $testRes.Output
    if (-not $testRes.Success) {
        Write-Warn "Tests failed. You can fix tests and re-run. Continue anyway? (y/N)"
        $cont2 = Read-Host "Continue despite failing tests?"
        if ($cont2.ToLower() -ne 'y') { Write-Err "Aborted by user due to failing tests."; exit 4 }
    } else { Write-Ok "Tests passed." }
}

## ---------------------- Step 6: Stage files (actual) ----------------------
Write-Info "\nStaging files: git add ."
$add = Run-Checked "git add ."
if (-not $add.Success) { Write-Err "git add failed: $($add.Output)"; exit 5 }

## Show staged files summary
Write-Info "\nStaged files summary (files to be committed):"
$staged = Run-Checked "git diff --name-only --cached"
if ($staged.Output) { Write-Host $staged.Output } else { Write-Info "No files staged to commit." }

## Show ignored files summary
Write-Info "\nIgnored files (by .gitignore):"
$ignored = Run-Checked "git ls-files --others -i --exclude-standard"
if ($ignored.Output) { Write-Host $ignored.Output } else { Write-Info "No ignored files detected or .gitignore is empty/missing." }

## ---------------------- Step 7: Commit ----------------------
Write-Info "\nPrepare initial commit message. Press Enter to accept the default."
$defaultMsg = "chore: initial project scaffolding (README, LICENSE, .gitignore, docs)"
$userMsg = Read-Host "Commit message [$defaultMsg]"
if ([string]::IsNullOrWhiteSpace($userMsg)) { $userMsg = $defaultMsg }

Write-Info "Committing..."
$commitRes = Run-Checked "git commit -m "$([regex]::Escape($userMsg))""
if (-not $commitRes.Success) {
    # If no changes, git commit may fail with "nothing to commit"
    if ($commitRes.Output -match 'nothing to commit') {
        Write-Warn "Nothing to commit. Perhaps files were already committed earlier."
    } else {
        Write-Err "git commit failed: $($commitRes.Output)"; exit 6
    }
} else {
    Write-Ok "Commit created.";
}

## ---------------------- Step 8: Rename branch to main ----------------------
Write-Info "Renaming current branch to 'main'..."
$branchRes = Run-Checked "git branch -M main"
if (-not $branchRes.Success) { Write-Warn "Branch rename may have failed: $($branchRes.Output)" } else { Write-Ok "Branch renamed to main." }

## ---------------------- Step 9: Configure remote origin ----------------------
Write-Info "\nConfigure remote repository on GitHub (no push performed by this script)."
$username = Read-Host "GitHub username or org (leave blank to skip setting remote)"
if (-not [string]::IsNullOrWhiteSpace($username)) {
    $repo = Read-Host "Repository name (will be created on GitHub if missing)"
    if ([string]::IsNullOrWhiteSpace($repo)) { Write-Warn "No repository name provided; skipping remote setup." }
    else {
        $proto = Read-Host "Protocol to use for remote: HTTPS or SSH? (h/s) [h]"
        if ([string]::IsNullOrWhiteSpace($proto)) { $proto = 'h' }
        if ($proto.ToLower().StartsWith('s')) {
            $remoteUrl = "git@github.com:$username/$repo.git"
        } else {
            $remoteUrl = "https://github.com/$username/$repo.git"
        }

        # If remote exists, ask before replacing
        $existingRemote = Run-Checked "git remote get-url origin"
        if ($existingRemote.Success) {
            Write-Warn "A remote 'origin' already exists: $($existingRemote.Output.Trim())"
            $replace = Read-Host "Replace existing remote 'origin' with $remoteUrl ? (y/N)"
            if ($replace.ToLower() -ne 'y') { Write-Info "Keeping existing remote." }
            else {
                $rm = Run-Checked "git remote remove origin"
                if (-not $rm.Success) { Write-Err "Failed to remove existing remote: $($rm.Output)"; exit 7 }
                $addRemote = Run-Checked "git remote add origin $remoteUrl"
                if (-not $addRemote.Success) { Write-Err "Failed to add remote: $($addRemote.Output)"; exit 8 }
                Write-Ok "Remote 'origin' updated to $remoteUrl"
            }
        } else {
            $addRemote = Run-Checked "git remote add origin $remoteUrl"
            if (-not $addRemote.Success) { Write-Err "Failed to add remote: $($addRemote.Output)"; exit 8 }
            Write-Ok "Remote 'origin' set to $remoteUrl"
        }
    }
} else {
    Write-Info "Skipping remote setup as username was not provided.";
}

## ---------------------- Final: Show status and push command ----------------------
Write-Host "\n--- Summary / Next steps ---" -ForegroundColor Magenta

$status = Run-Checked "git status --short --branch"
Write-Host $status.Output

Write-Info "Staged files (cached):"
$stagedNow = Run-Checked "git diff --name-only --cached"
Write-Host $stagedNow.Output

Write-Info "Ignored files sample (from .gitignore):"
$ignoredNow = Run-Checked "git ls-files --others -i --exclude-standard"
Write-Host $ignoredNow.Output

Write-Ok "Repository initialized locally."
if ($remoteUrl) { Write-Ok "Remote configured: $remoteUrl" }

Write-Host "\nWhen you are ready to publish to GitHub, run:" -ForegroundColor Cyan
Write-Host "    git push -u origin main" -ForegroundColor Green

Write-Host "\nIf you plan to deploy to Railway, ensure you add production environment variables to Railway and set up persistent storage for DATABASE_PATH and STATE_DIR." -ForegroundColor Yellow

Write-Ok "All done. Be careful: push only when you have verified no secrets are staged.";
