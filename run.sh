#!/usr/bin/env bash
# run.sh — TEK KOMUTLA kurulum + çalıştırma (Linux / macOS)
#
# Kullanım:
#     ./run.sh        (gerekirse önce: chmod +x run.sh)
#
# Yaptıkları (idempotent): venv kur, bağımlılıkları kur, ffmpeg/GPU yokla,
# pipeline'ı otomatik-kurtarma döngüsünde çalıştır.
set -uo pipefail
cd "$(dirname "$0")"

info() { printf '\033[36m[run] %s\033[0m\n' "$1"; }
warn() { printf '\033[33m[run] %s\033[0m\n' "$1"; }

# 1) Python
if ! command -v python3 >/dev/null 2>&1; then
    echo "python3 gerekli. (apt: sudo apt install python3 python3-venv)"; exit 1
fi

# 2) venv
PY=".venv/bin/python"
if [ ! -x "$PY" ]; then
    info "Sanal ortam oluşturuluyor (.venv)..."
    python3 -m venv .venv
fi

# 3) Bağımlılıklar (marker yoksa)
if [ ! -f ".venv/.installed" ]; then
    info "Bağımlılıklar kuruluyor (faster-whisper, yt-dlp)..."
    "$PY" -m pip install --upgrade pip
    "$PY" -m pip install -r requirements.txt
    touch .venv/.installed
fi

# 4) ffmpeg
if ! command -v ffmpeg >/dev/null 2>&1; then
    warn "ffmpeg bulunamadı. Kurun: (Linux) sudo apt install ffmpeg | (macOS) brew install ffmpeg"
fi

# 5) Donanım
if command -v nvidia-smi >/dev/null 2>&1; then
    info "GPU tespit edildi -> CUDA / float16 (hızlı mod)"
else
    info "GPU bulunamadı -> CPU / int8 (yavaş ama çalışır)"
fi

# 6) Otomatik-kurtarma döngüsü
count() {
    if [ -f dataset.json ]; then
        "$PY" -c "import json;print(len(json.load(open('dataset.json'))))" 2>/dev/null || echo 0
    else
        echo 0
    fi
}

fail=0
while true; do
    before="$(count)"
    info "Pipeline başlatılıyor... (mevcut kayıt: $before)"
    "$PY" pipeline.py
    code=$?
    after="$(count)"

    if [ "$code" -eq 0 ]; then
        info "Tamamlandı. Toplam kayıt: $after"; break
    fi

    warn "Pipeline $code koduyla durdu (kayıt: $before -> $after)."
    if [ "$after" -gt "$before" ]; then
        fail=0; warn "İlerleme var; yeniden başlatılıyor..."
    else
        fail=$((fail + 1))
        if [ -f current.txt ]; then
            poison="$(tr -d '[:space:]' < current.txt)"
            if [ -n "$poison" ]; then
                echo "$poison" >> skip.txt
                warn "Zehirli video skip.txt'e eklendi: $poison"
            fi
        fi
        if [ "$fail" -ge 3 ]; then warn "Üst üste 3 kez ilerleme yok. Durduruluyor."; exit 1; fi
        warn "İlerleme yok ($fail/3); zehirli video atlanıp tekrar denenecek..."
    fi
    sleep 3
done
