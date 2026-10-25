# vdo-skill setup for Windows. Run setup.bat (it calls this) - safe to run again any time.
#   1. Python 3.10-3.12 (installs 3.12 with winget if none is found)
#   2. ffmpeg (winget; falls back to the imageio-ffmpeg copy inside the venv)
#   3. .venv with the Python packages from requirements.txt
#   4. Kokoro voice model files into models\
#   5. The Claude skill: %USERPROFILE%\.claude\skills\vdo-video\SKILL.md  (+ dist\vdo-video-skill.zip to upload)
#   6. vdo doctor
param(
    [switch]$SkipSkill,
    [switch]$SkipModels
)

$ErrorActionPreference = 'Continue'   # native tools write to stderr; we check exit codes ourselves
$ProgressPreference = 'SilentlyContinue'
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

function Step($t) { Write-Host ""; Write-Host "== $t ==" -ForegroundColor Cyan }
function Ok($t)   { Write-Host "  [ok] $t" -ForegroundColor Green }
function Warn($t) { Write-Host "  [!!] $t" -ForegroundColor Yellow }
function Refresh-Path {
    $env:Path = [Environment]::GetEnvironmentVariable('Path', 'Machine') + ';' +
                [Environment]::GetEnvironmentVariable('Path', 'User') + ';' +
                (Join-Path $env:LOCALAPPDATA 'Microsoft\WinGet\Links')
}
function Has-Winget { return [bool](Get-Command winget -ErrorAction SilentlyContinue) }

# ---------------------------------------------------------------- 1. Python
Step "1/6 Python"
function Find-Python {
    $candidates = @(@('py', '-3.12'), @('py', '-3.11'), @('py', '-3.10'), @('python'), @('python3'))
    foreach ($c in $candidates) {
        $exe = $c[0]
        if (-not (Get-Command $exe -ErrorAction SilentlyContinue)) { continue }
        $pre = @()
        if ($c.Length -gt 1) { $pre = $c[1..($c.Length - 1)] }
        try {
            $v = & $exe @pre -c "import sys; print('%d.%d' % sys.version_info[:2])" 2>$null
        } catch { continue }
        if ($LASTEXITCODE -ne 0 -or -not $v) { continue }
        $parts = $v.Trim().Split('.')
        $minor = [int]$parts[1]
        if ([int]$parts[0] -eq 3 -and $minor -ge 10 -and $minor -le 13) {
            return @{ exe = $exe; pre = $pre; ver = $v.Trim() }
        }
    }
    return $null
}
$py = Find-Python
if (-not $py) {
    if (Has-Winget) {
        Write-Host "  installing Python 3.12 with winget..."
        winget install -e --id Python.Python.3.12 --scope user --accept-source-agreements --accept-package-agreements | Out-Host
        Refresh-Path
        $py = Find-Python
    }
}
if (-not $py) {
    Warn "Python 3.10-3.12 not found. Install it from https://www.python.org/downloads/ (tick 'Add python.exe to PATH'), then run setup.bat again."
    exit 1
}
Ok "Python $($py.ver)"

# ---------------------------------------------------------------- 2. ffmpeg
Step "2/6 ffmpeg"
Refresh-Path
if (Get-Command ffmpeg -ErrorAction SilentlyContinue) {
    Ok "ffmpeg found: $((Get-Command ffmpeg).Source)"
} elseif (Has-Winget) {
    Write-Host "  installing ffmpeg with winget (Gyan.FFmpeg)..."
    try {
        winget install -e --id Gyan.FFmpeg --accept-source-agreements --accept-package-agreements | Out-Host
    } catch { Warn "winget could not install ffmpeg: $_" }
    Refresh-Path
    if (Get-Command ffmpeg -ErrorAction SilentlyContinue) { Ok "ffmpeg installed" }
    else { Warn "ffmpeg not on PATH yet - the engine will use the copy from the imageio-ffmpeg package (open a new terminal later to pick up the system one)." }
} else {
    Warn "winget not available - the engine will use the imageio-ffmpeg copy. For the full ffmpeg: https://www.gyan.dev/ffmpeg/builds/"
}

# ---------------------------------------------------------------- 3. venv + packages
Step "3/6 Python packages (.venv)"
$venvPy = Join-Path $Root '.venv\Scripts\python.exe'
if (-not (Test-Path $venvPy)) {
    & $py.exe @($py.pre) -m venv (Join-Path $Root '.venv')
    if ($LASTEXITCODE -ne 0) { Warn "could not create .venv"; exit 1 }
}
& $venvPy -m pip install --upgrade pip --quiet --disable-pip-version-check
& $venvPy -m pip install -r (Join-Path $Root 'requirements.txt') --disable-pip-version-check
if ($LASTEXITCODE -ne 0) {
    Warn "pip install failed. If the error mentions onnxruntime, use Python 3.12 (winget install Python.Python.3.12), delete the .venv folder and run setup.bat again."
    exit 1
}
$ortOk = $true
try { & $venvPy -c "import onnxruntime" 2>$null; if ($LASTEXITCODE -ne 0) { $ortOk = $false } } catch { $ortOk = $false }
if (-not $ortOk) {
    Warn "onnxruntime failed to load - installing the Microsoft Visual C++ runtime it needs"
    if (Has-Winget) { winget install -e --id Microsoft.VCRedist.2015+.x64 --accept-source-agreements --accept-package-agreements | Out-Host }
    else { Warn "install https://aka.ms/vs/17/release/vc_redist.x64.exe then run setup.bat again" }
}
Ok "packages installed"

# ---------------------------------------------------------------- 4. Kokoro voice model
Step "4/6 Kokoro voice model"
$models = Join-Path $Root 'models'
New-Item -ItemType Directory -Force -Path $models | Out-Null
$base = 'https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0'
$files = @(@{ name = 'kokoro-v1.0.onnx'; min = 300MB }, @{ name = 'voices-v1.0.bin'; min = 20MB })
if (-not $SkipModels) {
    foreach ($f in $files) {
        $dst = Join-Path $models $f.name
        if ((Test-Path $dst) -and ((Get-Item $dst).Length -ge $f.min)) { Ok "$($f.name) already there"; continue }
        Write-Host "  downloading $($f.name) ..."
        $url = "$base/$($f.name)"
        $tmp = "$dst.part"
        if (Get-Command curl.exe -ErrorAction SilentlyContinue) {
            curl.exe -L --fail --retry 3 -o $tmp $url
        } else {
            Invoke-WebRequest -Uri $url -OutFile $tmp -UseBasicParsing
        }
        if ((Test-Path $tmp) -and ((Get-Item $tmp).Length -ge $f.min)) {
            Move-Item -Force $tmp $dst
            Ok "$($f.name) downloaded"
        } else {
            Warn "download of $($f.name) failed - download it yourself from $url into $models"
        }
    }
}

# ---------------------------------------------------------------- 5. Claude skill
Step "5/6 Claude skill"
$skillSrc = Join-Path $Root 'skill\vdo-video\SKILL.md'
$text = (Get-Content -Raw -Encoding UTF8 $skillSrc).Replace('{{VDO_HOME}}', $Root.TrimEnd('\'))
$dist = Join-Path $Root 'dist\vdo-video'
New-Item -ItemType Directory -Force -Path $dist | Out-Null
[IO.File]::WriteAllText((Join-Path $dist 'SKILL.md'), $text, (New-Object Text.UTF8Encoding $false))
$zip = Join-Path $Root 'dist\vdo-video-skill.zip'
if (Test-Path $zip) { Remove-Item $zip -Force }
Compress-Archive -Path $dist -DestinationPath $zip
Ok "skill package for the Claude app: $zip"
if (-not $SkipSkill) {
    $target = Join-Path $env:USERPROFILE '.claude\skills\vdo-video'
    New-Item -ItemType Directory -Force -Path $target | Out-Null
    [IO.File]::WriteAllText((Join-Path $target 'SKILL.md'), $text, (New-Object Text.UTF8Encoding $false))
    Ok "installed for Claude Code: $target\SKILL.md"
}

# ---------------------------------------------------------------- 6. doctor
Step "6/6 Check"
& (Join-Path $Root 'vdo.bat') doctor
if ($LASTEXITCODE -eq 0) {
    Write-Host ""
    Write-Host "Setup complete." -ForegroundColor Green
    Write-Host "Test render (uses the sample pictures):  vdo.bat build projects\greece_sample\project.json"
    Write-Host "Then in Claude: paste a script and say 'make a video of this'."
} else {
    Warn "Setup finished with problems - read the [!!] lines above (README.md > Troubleshooting)."
}
