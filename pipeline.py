# -*- coding: utf-8 -*-
"""
pipeline.py — YouTube Matematik/Geometri Soru Çözüm Veri Fabrikası.

Akış:
  links.txt -> (yt-dlp) ses indir -> ham videoyu sil -> (faster-whisper large-v3,
  tr, beam_size=5) deşifre -> (cleaner) temizle + LaTeX -> dataset.json'a append.

Tasarım ilkeleri:
  * Idempotent  : dataset.json'da olan video_id'ler atlanır, veri ezilmez.
  * Resumable   : crash sonrası kaldığı yerden devam eder.
  * Crash-safe  : dataset.json atomik (tmp + replace) yazılır.
  * 0 TL API    : her şey yereldir (yerel GPU/CPU). Harici ücretli API yok.
  * Donanıma uyum: CUDA varsa float16, yoksa int8.

Bağımlılıklar (run.ps1 / run.sh bunları kurar): faster-whisper, yt-dlp, ffmpeg.
"""
import json
import os
import sys
import shutil
import glob
from datetime import datetime

from cleaner import clean_transcript, split_steps

BASE = os.path.dirname(os.path.abspath(__file__))
LINKS_FILE = os.path.join(BASE, "links.txt")
DATASET_FILE = os.path.join(BASE, "dataset.json")
SKIP_FILE = os.path.join(BASE, "skip.txt")
LOG_FILE = os.path.join(BASE, "run_all.log")
AUDIO_DIR = os.path.join(BASE, "audio")
CURRENT_FILE = os.path.join(BASE, "current.txt")  # otomatik-kurtarma için "şu an işlenen"

MODEL_NAME = os.environ.get("WHISPER_MODEL", "large-v3")
LANGUAGE = os.environ.get("WHISPER_LANG", "tr")
BEAM_SIZE = int(os.environ.get("WHISPER_BEAM", "5"))


# --------------------------------------------------------------------------- #
# Loglama (hem ekrana hem run_all.log'a)
# --------------------------------------------------------------------------- #
def log(msg: str) -> None:
    line = f"[{datetime.now().strftime('%H:%M:%S')}] {msg}"
    print(line, flush=True)
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError:
        pass


# --------------------------------------------------------------------------- #
# Donanım tespiti -> (device, compute_type)
# --------------------------------------------------------------------------- #
def detect_device():
    dev = os.environ.get("WHISPER_DEVICE")
    ct = os.environ.get("WHISPER_COMPUTE_TYPE")
    if dev:
        return dev, ct or ("float16" if dev == "cuda" else "int8")
    try:
        import ctranslate2
        if ctranslate2.get_cuda_device_count() > 0:
            return "cuda", ct or "float16"
    except Exception:
        pass
    return "cpu", ct or "int8"


# --------------------------------------------------------------------------- #
# Girdi/çıktı yardımcıları
# --------------------------------------------------------------------------- #
def read_links(path: str):
    if not os.path.exists(path):
        log(f"UYARI: {os.path.basename(path)} bulunamadı, boş liste.")
        return []
    out = []
    with open(path, encoding="utf-8") as f:
        for raw in f:
            line = raw.strip()
            if not line or line.startswith("#"):  # boş ve yorum satırlarını atla
                continue
            out.append(line)
    return out


def read_skip(path: str):
    if not os.path.exists(path):
        return set()
    with open(path, encoding="utf-8") as f:
        return {ln.strip() for ln in f if ln.strip() and not ln.startswith("#")}


def load_dataset(path: str):
    if not os.path.exists(path):
        return []
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except (json.JSONDecodeError, OSError) as e:
        # Bozuk dosyayı ezme; yedekle ve boştan başla
        backup = path + ".corrupt"
        try:
            shutil.copy2(path, backup)
            log(f"UYARI: dataset.json okunamadı ({e}); yedek: {os.path.basename(backup)}")
        except OSError:
            pass
        return []


def save_dataset(path: str, data) -> None:
    """Atomik yazım: önce .tmp'ye yaz, sonra yerine koy (crash-safe)."""
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def write_text(path: str, text: str) -> None:
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def safe_remove(path: str) -> None:
    try:
        os.remove(path)
    except OSError:
        pass


def cleanup_audio(video_id: str) -> None:
    """Bu videoya ait tüm ses/ara dosyaları sil (disk optimizasyonu)."""
    for p in glob.glob(os.path.join(AUDIO_DIR, video_id + ".*")):
        safe_remove(p)


# --------------------------------------------------------------------------- #
# yt-dlp: link içindeki videoları say + indir
# --------------------------------------------------------------------------- #
def iter_video_ids(link: str):
    """Tek video ya da oynatma listesi -> video_id'leri üretir."""
    import yt_dlp
    opts = {
        "quiet": True, "no_warnings": True, "skip_download": True,
        "extract_flat": "in_playlist",
    }
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(link, download=False)
    if not info:
        return
    if info.get("_type") == "playlist" or "entries" in info:
        for e in info.get("entries") or []:
            if e and e.get("id"):
                yield e["id"]
    elif info.get("id"):
        yield info["id"]


def download_audio(video_id: str) -> str:
    """Videoyu indir, sadece sesi mp3'e ayıkla, ham videoyu sil. mp3 yolunu döndür."""
    import yt_dlp
    url = f"https://www.youtube.com/watch?v={video_id}"
    out_tmpl = os.path.join(AUDIO_DIR, video_id + ".%(ext)s")
    opts = {
        "format": "bestaudio/best",
        "outtmpl": out_tmpl,
        "quiet": True, "no_warnings": True, "noprogress": True,
        "keepvideo": False,  # ayıklamadan sonra ham dosyayı tut-ma
        "postprocessors": [{
            "key": "FFmpegExtractAudio",
            "preferredcodec": "mp3",
            "preferredquality": "192",
        }],
    }
    with yt_dlp.YoutubeDL(opts) as ydl:
        ydl.download([url])
    mp3 = os.path.join(AUDIO_DIR, video_id + ".mp3")
    if not os.path.exists(mp3):
        raise FileNotFoundError(f"Ses ayıklanamadı: {mp3}")
    return mp3


# --------------------------------------------------------------------------- #
# faster-whisper: ses -> ham metin
# --------------------------------------------------------------------------- #
def load_model():
    from faster_whisper import WhisperModel
    device, compute = detect_device()
    log(f"Model yükleniyor: {MODEL_NAME} | device={device} compute_type={compute}")
    return WhisperModel(MODEL_NAME, device=device, compute_type=compute)


def transcribe(model, audio_path: str) -> str:
    segments, _info = model.transcribe(audio_path, language=LANGUAGE, beam_size=BEAM_SIZE)
    return " ".join(seg.text.strip() for seg in segments).strip()


# --------------------------------------------------------------------------- #
# Ana akış
# --------------------------------------------------------------------------- #
def main() -> int:
    os.makedirs(AUDIO_DIR, exist_ok=True)

    links = read_links(LINKS_FILE)
    skip = read_skip(SKIP_FILE)
    data = load_dataset(DATASET_FILE)
    done = {r["video_id"] for r in data if isinstance(r, dict) and "video_id" in r}

    log(f"Başlangıç: {len(links)} link | {len(done)} mevcut kayıt | {len(skip)} skip")
    if not links:
        log("links.txt boş — yapılacak iş yok.")
        return 0

    model = None  # ilk gerçek işte tembel yüklenir (gereksiz model yüklemesini önler)
    new_count = 0

    for link in links:
        try:
            video_ids = list(iter_video_ids(link))
        except Exception as e:
            log(f"HATA: link çözümlenemedi ({link}): {e}")
            continue

        for vid in video_ids:
            if vid in done:
                continue                      # idempotency: zaten işlenmiş
            if vid in skip:
                log(f"Atlandı (skip.txt): {vid}")
                continue

            write_text(CURRENT_FILE, vid)     # kurtarma için "şu an işleniyor"
            try:
                if model is None:
                    model = load_model()

                log(f"İndiriliyor: {vid}")
                audio = download_audio(vid)

                log(f"Deşifre ediliyor: {vid}")
                raw = transcribe(model, audio)

                cleaned = clean_transcript(raw)
                record = {
                    "video_id": vid,
                    "raw_transcript": cleaned,
                    "cot_steps": split_steps(cleaned),
                    "processed_at": datetime.now().isoformat(timespec="seconds"),
                }
                data.append(record)
                save_dataset(DATASET_FILE, data)   # her kayıttan sonra kalıcı (crash-safe)
                done.add(vid)
                new_count += 1
                log(f"✓ {vid} işlendi — toplam {len(data)} kayıt")
            except KeyboardInterrupt:
                log("Kullanıcı durdurdu (Ctrl+C).")
                return 130
            except Exception as e:
                # Bir video patlarsa pipeline durmaz; logla ve devam et.
                log(f"HATA ({vid}): {e}")
            finally:
                cleanup_audio(vid)             # diski temiz tut

    safe_remove(CURRENT_FILE)
    log(f"Bitti. Bu turda +{new_count} yeni kayıt, toplam {len(data)}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
