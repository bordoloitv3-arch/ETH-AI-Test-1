<#
complete_upload.ps1

Automates the final local steps to get your repository onto GitHub.

What this script does (interactive):
- Checks for Git; attempts to install via winget if missing (if winget available).
- Runs the `init_repo.ps1` script (safe to run again).
- Optionally opens the GitHub "Create repository" page for you.
- Accepts a remote URL you paste (or detects an existing remote).
- Runs `git push -u origin main` to upload your code.

Notes:
- This script must be run on your local Windows machine where Git will be available.
- The script does not create a GitHub personal access token (PAT) - you must provide it when prompted by Git.
- If you want full automation of repo creation, install the GitHub CLI (`gh`) and authenticate separately.
#>

function Write-Info($m){ Write-Host $m -ForegroundColor Cyan }
function Write-Ok($m){ Write-Host $m -ForegroundColor Green }
function Write-Warn($m){ Write-Host $m -ForegroundColor Yellow }
function Write-Err($m){ Write-Host $m -ForegroundColor Red }

Write-Host "`n=== Complete Upload Helper ===" -ForegroundColor Magenta

# Check for git
$git = Get-Command git -ErrorAction SilentlyContinue
if (-not $git) {
    Write-Warn "Git not found on this machine. Attempting to install via winget (if available)."
    $winget = Get-Command winget -ErrorAction SilentlyContinue
    if ($winget) {
        Write-Info "Running: winget install --id Git.Git -e --source winget"
        try {
            Start-Process -FilePath winget -ArgumentList 'install --id Git.Git -e --source winget' -NoNewWindow -Wait
        } catch {
            Write-Warn "winget install failed or required elevation. Please install Git manually from https://git-scm.com/download/win and re-run this script."
            exit 1
        }
        Write-Ok "winget install finished. Please restart PowerShell and re-run this script if git is still not available.";
        # Re-check
        $git = Get-Command git -ErrorAction SilentlyContinue
        if (-not $git) { Write-Err "Git still not found. Install manually and re-run."; exit 1 }
    } else {
        Write-Err "winget not available. Please install Git from https://git-scm.com/download/win and re-run this script."; exit 1
    }
}

Write-Ok "Git found: $($git.Path)"

# Run init_repo.ps1 to ensure repo is initialized and staged
if (Test-Path -Path .\init_repo.ps1) {
    Write-Info "Running init_repo.ps1 (safe to run again)..."
    powershell -ExecutionPolicy Bypass -File .\init_repo.ps1
} else {
    Write-Warn "init_repo.ps1 not found in current folder. Please run it manually first.";
}

# Show current git remote if any
Write-Info "\nChecking existing git remote (origin)..."
try {
    $remote = git remote get-url origin 2>$null
} catch {
    $remote = $null
}
if ($remote) { Write-Ok "Existing remote: $remote" }
else { Write-Warn "No remote 'origin' configured." }

# Offer to open GitHub create page
$openGH = Read-Host "Do you want me to open the GitHub 'Create repository' page in your browser now? (y/N)"
if ($openGH.ToLower() -eq 'y') {
    Start-Process "https://github.com/new"
    Write-Info "The browser opened. Create a repository (do NOT initialize with README/gitignore/license). After creating it, copy the HTTPS repo URL (https://github.com/your-username/your-repo.git) and paste it when prompted below."
}

# Ask for remote URL if not present
if (-not $remote) {
    $remoteUrl = Read-Host "Paste the GitHub repository HTTPS URL (or leave blank to skip remote setup)"
    if (-not [string]::IsNullOrWhiteSpace($remoteUrl)) {
        Write-Info "Adding remote origin: $remoteUrl"
        $add = git remote add origin $remoteUrl 2>&1
        if ($LASTEXITCODE -ne 0) { Write-Err "Failed to add remote: $add"; exit 1 }
        Write-Ok "Remote 'origin' added."
    } else {
        Write-Warn "No remote URL provided. You can add it later with: git remote add origin <URL>"
    }
} else {
    Write-Info "Using existing remote: $remote"
}

# Confirm push
$doPush = Read-Host "Ready to push local 'main' to remote 'origin'? This will upload your code. Proceed? (y/N)"
if ($doPush.ToLower() -ne 'y') { Write-Warn "Push cancelled by user. You can run 'git push -u origin main' later."; exit 0 }

Write-Info "Pushing to remote..."
try {
    git push -u origin main
    if ($LASTEXITCODE -eq 0) { Write-Ok "Push successful. Visit your GitHub repo in the browser to verify." }
    else { Write-Err "git push returned non-zero exit code. See the output above for details."; exit 1 }
} catch {
    Write-Err "git push failed: $_"; exit 1
}

Write-Ok "All done. To verify, run: git log --oneline && git remote -v"
