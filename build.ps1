# build.ps1 — BinarySlicer one-file build (no fragile line continuations)

$ErrorActionPreference = "Stop"

# Go to the script directory (repo root)
Set-Location -Path (Split-Path -Parent $MyInvocation.MyCommand.Path)

# Optional: activate local venv if present
$venv = ".\.venv\Scripts\Activate.ps1"
if (Test-Path $venv) { . $venv }

# Ensure PyInstaller is available
try {
    pyinstaller --version | Out-Null
} catch {
    python -m pip install --upgrade pip
    python -m pip install pyinstaller
}

# Clean previous artifacts
Remove-Item -Recurse -Force -ErrorAction SilentlyContinue build, dist, *.spec

# Build using splatted args (no backticks, no carets)
$piArgs = @(
    "--clean",
    "-F",
    "-w",
    "-n", "BinarySlicer",
    "-i", "icons\jci_globe.ico",
    "--collect-data", "binaryslicer",
    "--add-data", "icons;icons",
    "-m", "binaryslicer.ui"
)

& pyinstaller @piArgs

Write-Host "`n✅ Build complete. EXE at: $(Resolve-Path .\dist\BinarySlicer.exe)" -ForegroundColor Green
