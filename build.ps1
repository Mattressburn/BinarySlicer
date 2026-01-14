# build.ps1 — BinarySlicer one-file build with date-based versioning

$ErrorActionPreference = "Stop"

# Auto-generate version based on today's date (YYYY.MM.DD)
$versionFull = Get-Date -Format "yyyy.MM.dd"
$y,$m,$d = $versionFull -split '\.'
$y = [int]$y
$m = [int]$m
$d = [int]$d

Write-Host "Building BinarySlicer version $versionFull..."

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

# --- Begin robust APP_VERSION patch (PowerShell-safe) ---
$uiPath    = 'binaryslicer/ui.py'
$uiContent = Get-Content -Path $uiPath -Raw
$pattern   = 'APP_VERSION\s*=\s*".*?"'  # single-quoted regex
# Build replacement string without escaping using format operator
$replacement = 'APP_VERSION = "{0}"' -f $versionFull

if ($uiContent -match $pattern) {
    $uiContent = $uiContent -replace $pattern, $replacement
} else {
    # Insert APP_VERSION after imports if present; otherwise prepend
    $lines = $uiContent -split "`r?`n"
    $lastImport = ($lines | Select-String -Pattern '^\s*(import|from)\s+' | Select-Object -Last 1)
    if ($lastImport) {
        $idx = $lastImport.LineNumber
        $before = $lines[0..($idx - 1)]
        $after  = $lines[$idx..($lines.Length - 1)]
        $uiContent = ($before + $replacement + $after) -join "`r`n"
    } else {
        $uiContent = $replacement + "`r`n" + $uiContent
    }
}
Set-Content -Path $uiPath -Value $uiContent -Encoding UTF8
# --- End robust APP_VERSION patch ---

# Generate version.txt for PyInstaller (VSVersionInfo) using non-padded integers
$versionText = @"
VSVersionInfo(
    ffi=FixedFileInfo(
        filevers=($y,$m,$d,0),
        prodvers=($y,$m,$d,0),
        mask=0x3f,
        flags=0x0,
        OS=0x40004,
        fileType=0x1,
        subtype=0x0,
        date=(0, 0)
    ),
    kids=[
        StringFileInfo([
            StringTable('040904B0', [
                StringStruct('CompanyName', 'BinarySlicer'),
                StringStruct('FileDescription', 'BinarySlicer'),
                StringStruct('FileVersion', '$versionFull'),
                StringStruct('ProductName', 'BinarySlicer'),
                StringStruct('ProductVersion', '$versionFull')
            ])
        ]),
        VarFileInfo([VarStruct('Translation', [0x0409, 1200])])
    ]
)
"@
Set-Content -Path "version.txt" -Value $versionText -Encoding UTF8

# Build using splatted args (no backticks, no carets)
$piArgs = @(
    "--clean",
    "-F",
    "-w",
    "-n", "BinarySlicer-$versionFull",
    "-i", "icons\jci_globe.ico",
    "--version-file", "version.txt",
    "--collect-data", "binaryslicer",
    "--add-data", "icons;icons",
    "--collect-all", "PySide6",
    "--collect-submodules", "PySide6",
    "--hidden-import", "PySide6",
    "--hidden-import", "PySide6.QtCore",
    "--hidden-import", "PySide6.QtGui",
    "--hidden-import", "PySide6.QtWidgets"
)

$piArgs += ".\binaryslicer.py"

python -m PyInstaller @piArgs

$exePath = Resolve-Path "./dist/BinarySlicer-$versionFull.exe" -ErrorAction SilentlyContinue
if (-not $exePath) {
    $exePath = Join-Path "dist" "BinarySlicer-$versionFull.exe"
}

if (Test-Path $exePath) {
    Write-Host "`nBuild complete. EXE at: $exePath" -ForegroundColor Green
    try {
        $hash = (Get-FileHash $exePath -Algorithm SHA256).Hash
        Write-Host "SHA256: $hash" -ForegroundColor Green
    } catch {
        Write-Warning "SHA256 failed: $_"
    }
} else {
    Write-Host "`n❌ Build failed; EXE not found at $exePath" -ForegroundColor Red
}
