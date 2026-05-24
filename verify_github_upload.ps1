#!/usr/bin/env powershell
<#
verify_github_upload.ps1

Beginner-friendly verification script to confirm your GitHub upload was successful.
Run this AFTER you've pushed to GitHub and created your repository.

Usage: .\verify_github_upload.ps1

#>

function Write-Ok($msg) { Write-Host "✓ $msg" -ForegroundColor Green }
function Write-Warn($msg) { Write-Host "⚠ $msg" -ForegroundColor Yellow }
function Write-Info($msg) { Write-Host "ℹ $msg" -ForegroundColor Cyan }
function Write-Err($msg) { Write-Host "✗ $msg" -ForegroundColor Red }

Write-Host "`n=== GitHub Upload Verification ===" -ForegroundColor Magenta

## Check 1: Local Git status
Write-Info "Check 1: Local Git status..."
$log = git log --oneline -1 2>&1
if ($LASTEXITCODE -eq 0) {
    Write-Ok "Git repository exists"
    Write-Host $log
} else {
    Write-Err "No Git repository found"; exit 1
}

## Check 2: Remote configured
Write-Info "Check 2: Remote 'origin' configured..."
$remoteUrl = git remote get-url origin 2>&1
if ($LASTEXITCODE -eq 0) {
    Write-Ok "Remote found: $remoteUrl"
} else {
    Write-Err "Remote 'origin' not found"; exit 2
}

## Check 3: Upstream tracking
Write-Info "Check 3: Checking origin/main tracking..."
$tracking = git status --porcelain --branch 2>&1 | Select-Object -First 1
Write-Host $tracking
if ($tracking -match 'origin/main') {
    Write-Ok "Upstream branch 'origin/main' is tracked"
} else {
    Write-Warn "Upstream tracking not set — run: git push -u origin main"
}

## Check 4: Extract repo details
Write-Info "Check 4: Extracting repository details..."
if ($remoteUrl -match 'github\.com[:/]([^/]+)/(.+?)(?:\.git)?$') {
    $username = $matches[1]
    $reponame = $matches[2] -replace '\.git$', ''
    $githubUrl = "https://github.com/$username/$reponame"
    Write-Ok "GitHub repository: $githubUrl"
} else {
    Write-Warn "Could not extract GitHub URL from remote"; $githubUrl = $null
}

## Check 5: Staged files (should be empty if all committed)
Write-Info "Check 5: Checking for uncommitted changes..."
$status = git status --short 2>&1
if ([string]::IsNullOrWhiteSpace($status)) {
    Write-Ok "All changes committed (no pending changes)"
} else {
    Write-Warn "Uncommitted changes exist:"
    Write-Host $status
}

## Check 6: Dangerous files
Write-Info "Check 6: Checking for dangerous files in commit history..."
$dangerous = $false
$patterns = @('\.env', '\.sqlite', '\.db', 'secrets', 'password', 'KEY')
foreach ($pattern in $patterns) {
    $found = git log -p --all -S $pattern 2>&1 | Select-Object -First 1
    if ($found) {
        Write-Warn "Found reference to '$pattern' in history"
        $dangerous = $true
    }
}
if (-not $dangerous) {
    Write-Ok "No dangerous patterns found in commit history"
}

## Check 7: Branch name
Write-Info "Check 7: Verifying branch name..."
$branch = git rev-parse --abbrev-ref HEAD 2>&1
if ($branch -eq 'main') {
    Write-Ok "On branch 'main'"
} else {
    Write-Warn "On branch '$branch' (expected 'main')"
}

## Check 8: Commit count
Write-Info "Check 8: Checking commit count..."
$commitCount = (git rev-list --count HEAD 2>&1) | Select-Object -First 1
Write-Ok "Total commits: $commitCount"

Write-Host "`n=== Summary ===" -ForegroundColor Magenta
Write-Ok "Local repository is ready"
if ($githubUrl) {
    Write-Ok "GitHub repository: $githubUrl"
    Write-Info "Next steps:"
    Write-Host "  1) Visit GitHub in browser: $githubUrl"
    Write-Host "  2) Verify files are present (README.md, LICENSE, docs/)"
    Write-Host "  3) Search for '.env' — should return no results"
    Write-Host "  4) See docs/RAILWAY_NEXT_STEPS.md for deployment"
}

