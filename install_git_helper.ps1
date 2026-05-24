<#
install_git_helper.ps1

Helper script to download and launch the Git for Windows installer if Git
is not available on the system. This script must be run locally on your
Windows machine. It will:

- Check if `git` is on PATH.
- If missing, download the latest Git for Windows installer and launch it
  with elevation. It will not run the installer silently — you will need
  to follow the installer UI and choose the recommended option "Use Git
  from the command line and also from 3rd-party software".
- After installer finishes, reopen PowerShell and re-run `complete_upload.ps1`.

Usage (PowerShell):

    cd 'F:\Trading AI 2'
    .\install_git_helper.ps1

Notes:
- The download URL uses Git for Windows latest GitHub redirect. If the
  URL changes in future, download manually from https://git-scm.com/download/win
- This script must be run interactively because the installer requires
  UI interaction and UAC elevation.
#>

function Write-Info($m){ Write-Host $m -ForegroundColor Cyan }
function Write-Ok($m){ Write-Host $m -ForegroundColor Green }
function Write-Warn($m){ Write-Host $m -ForegroundColor Yellow }
function Write-Err($m){ Write-Host $m -ForegroundColor Red }

Write-Host "`n=== install_git_helper.ps1 ===" -ForegroundColor Magenta

# Check for git
$git = Get-Command git -ErrorAction SilentlyContinue
if ($git) {
    Write-Ok "Git is already installed: $($git.Path)"
    Write-Info "If you intended to push now, run: powershell -ExecutionPolicy Bypass -File .\complete_upload.ps1"
    exit 0
}

Write-Warn "Git not found on this system. Preparing to download Git for Windows installer..."

# Where to download
$installerUrl = 'https://github.com/git-for-windows/git/releases/latest/download/Git-64-bit.exe'
$tempPath = Join-Path $env:TEMP 'Git-Installer.exe'

if (Test-Path $tempPath) { Remove-Item $tempPath -Force }

Write-Info "Downloading installer from: $installerUrl"
try {
    Invoke-WebRequest -Uri $installerUrl -OutFile $tempPath -UseBasicParsing -ErrorAction Stop
    Write-Ok "Downloaded installer to: $tempPath"
} catch {
  Write-Err "Download failed: $($_.Exception.Message)"
  Write-Warn "Automatic download failed — network or server issue."
  Write-Info "Opening the download page in your default browser so you can download the installer manually."
  try {
    Start-Process "https://git-scm.com/download/win"
    Write-Info "Browser opened to https://git-scm.com/download/win. Please download the Git for Windows installer and run it."
    Write-Info "After installation finishes, close and re-open PowerShell, then run: .\\complete_upload.ps1"
  } catch {
    Write-Err "Could not open browser automatically. Please open https://git-scm.com/download/win in your browser and download the installer manually."
  }
  exit 1
}

Write-Info "Launching Git installer (you will be prompted for Administrator access). Follow the installer UI and choose the recommended options."
try {
    Start-Process -FilePath $tempPath -Verb RunAs
    Write-Ok "Installer launched. Complete the wizard, ensuring you select 'Use Git from the command line' when prompted.";
    Write-Info "After installation finishes, close and re-open PowerShell, then run: .\\complete_upload.ps1"
} catch {
    Write-Err "Failed to launch installer: $($_.Exception.Message)"
    Write-Err "You can run the installer manually from: $tempPath or download it from https://git-scm.com/download/win"
    exit 1
}
