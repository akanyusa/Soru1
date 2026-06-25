#Requires -Version 5.1
<#
  run.ps1 — TEK KOMUTLA kurulum + çalıştırma (Windows / PowerShell)

  Kullanım:
      .\run.ps1

  Yaptıkları (hepsi idempotent — varsa atlar):
    1) Python kontrolü
    2) .venv sanal ortamını oluşturur
    3) Bağımlılıkları kurar (faster-whisper, yt-dlp)
    4) ffmpeg kontrolü (yoksa winget ile kurmayı dener / yönlendirir)
    5) Donanımı yoklar (nvidia-smi -> CUDA float16 / yoksa CPU int8)
    6) pipeline'ı OTOMATİK-KURTARMA döngüsünde çalıştırır
       (çökerse yeniden başlar; ilerleme yoksa zehirli videoyu skip.txt'e ekler;
        üst üste 3 kez ilerleme olmazsa durur)
#>
$ErrorActionPreference = "Stop"
$root = $PSScriptRoot
Set-Location $root

function Info($m) { Write-Host "[run] $m" -ForegroundColor Cyan }
function Warn($m) { Write-Host "[run] $m" -ForegroundColor Yellow }

# 1) Python ----------------------------------------------------------------
if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    throw "Python bulunamadı. https://www.python.org/downloads/ adresinden kurup 'Add to PATH' seçeneğini işaretleyin."
}

# 2) venv ------------------------------------------------------------------
$venv  = Join-Path $root ".venv"
$pyExe = Join-Path $venv "Scripts\python.exe"
if (-not (Test-Path $pyExe)) {
    Info "Sanal ortam oluşturuluyor (.venv)..."
    python -m venv $venv
}

# 3) Bağımlılıklar (marker yoksa kur) --------------------------------------
$marker = Join-Path $venv ".installed"
if (-not (Test-Path $marker)) {
    Info "Bağımlılıklar kuruluyor (faster-whisper, yt-dlp)..."
    & $pyExe -m pip install --upgrade pip
    & $pyExe -m pip install -r (Join-Path $root "requirements.txt")
    if ($LASTEXITCODE -ne 0) { throw "pip kurulumu başarısız." }
    New-Item -ItemType File -Path $marker -Force | Out-Null
}

# 4) ffmpeg ----------------------------------------------------------------
if (-not (Get-Command ffmpeg -ErrorAction SilentlyContinue)) {
    Warn "ffmpeg bulunamadı. winget ile kurulmayı deniyorum..."
    try {
        winget install --id Gyan.FFmpeg -e --source winget `
            --accept-package-agreements --accept-source-agreements
        Warn "ffmpeg kuruldu. PATH'in güncellenmesi için bu terminali kapatıp yeniden açmanız gerekebilir."
    } catch {
        Warn "ffmpeg otomatik kurulamadı. Lütfen elle kurun: https://www.gyan.dev/ffmpeg/builds/ (zip'i açıp 'bin' klasörünü PATH'e ekleyin)."
    }
}

# 5) Donanım bilgisi -------------------------------------------------------
if (Get-Command nvidia-smi -ErrorAction SilentlyContinue) {
    $gpu = (nvidia-smi --query-gpu=name --format=csv,noheader) -join ", "
    Info "GPU tespit edildi: $gpu  ->  CUDA / float16 (hızlı mod)"
} else {
    Info "GPU bulunamadı  ->  CPU / int8 (yavaş ama çalışır)"
}

# 6) Otomatik-kurtarma döngüsü ---------------------------------------------
$dataset = Join-Path $root "dataset.json"
$skip    = Join-Path $root "skip.txt"
$current = Join-Path $root "current.txt"

function Get-RecordCount {
    if (Test-Path $dataset) {
        try { return @(Get-Content $dataset -Raw | ConvertFrom-Json).Count } catch { return 0 }
    }
    return 0
}

$fail = 0
while ($true) {
    $before = Get-RecordCount
    Info "Pipeline başlatılıyor... (mevcut kayıt: $before)"
    & $pyExe (Join-Path $root "pipeline.py")
    $code  = $LASTEXITCODE
    $after = Get-RecordCount

    if ($code -eq 0) {
        Info "Tamamlandı. Toplam kayıt: $after"
        break
    }

    Warn "Pipeline $code koduyla durdu (kayıt: $before -> $after)."
    if ($after -gt $before) {
        $fail = 0
        Warn "İlerleme var; yeniden başlatılıyor..."
    } else {
        $fail++
        if (Test-Path $current) {
            $poison = (Get-Content $current -Raw).Trim()
            if ($poison) {
                Add-Content -Path $skip -Value $poison -Encoding UTF8
                Warn "Zehirli video skip.txt'e eklendi: $poison"
            }
        }
        if ($fail -ge 3) { throw "Üst üste 3 kez ilerleme sağlanamadı. Durduruluyor." }
        Warn "İlerleme yok ($fail/3); zehirli video atlanıp tekrar denenecek..."
    }
    Start-Sleep -Seconds 3
}
