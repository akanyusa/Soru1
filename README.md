# YouTube Matematik/Geometri Soru Çözüm Veri Fabrikası

YKS soru-çözüm videolarını **uçtan uca**, **tamamen yerel** ve **0 TL dış API maliyetiyle** işleyip yapılandırılmış bir veri setine (`dataset.json`) dönüştüren pipeline.

> Akış: `links.txt` → **yt-dlp** ile ses indir (ham videoyu anında sil) → **faster-whisper** `large-v3` ile deşifre (`tr`, `beam_size=5`) → **temizlik + LaTeX sihirbazı** → `dataset.json`'a idempotent append.

Tüm hesaplama yerel donanımında çalışır: **NVIDIA GPU varsa** `float16` (hızlı), **yoksa CPU** `int8` (yavaş ama çalışır). Otomatik tespit edilir.

---

## 🚀 Tek komutla başlat

Önce `links.txt` içine kendi YouTube linklerini yaz, sonra:

**Windows (PowerShell):**
```powershell
.\run.ps1
```

**Linux / macOS:**
```bash
chmod +x run.sh && ./run.sh
```

Bu komut **her şeyi** yapar (idempotent — kuruluysa atlar):
1. Python'u kontrol eder
2. `.venv` sanal ortamı kurar
3. Bağımlılıkları kurar (`faster-whisper`, `yt-dlp`)
4. `ffmpeg`'i kontrol eder (Windows'ta `winget` ile kurmayı dener, yoksa yönlendirir)
5. Donanımı yoklar (`nvidia-smi`) → CUDA/float16 ya da CPU/int8
6. Pipeline'ı **otomatik-kurtarma** döngüsünde çalıştırır

---

## 🧩 Mimari / dosyalar

| Dosya | Görevi |
|---|---|
| `pipeline.py` | Ana akış: indir → deşifre → temizle → kaydet. Idempotent & crash-safe. |
| `cleaner.py` | Türkçe metin temizliği + konuşma dilini **LaTeX**'e çeviren regex sihirbazı. |
| `run.ps1` / `run.sh` | Tek-komut kurulum + otomatik-kurtarma döngüsü. |
| `requirements.txt` | Python bağımlılıkları. |
| `links.txt` | İşlenecek YouTube linkleri (video veya oynatma listesi). |
| `test_cleaner.py` | `cleaner.py` için doğrulama testleri (`python test_cleaner.py`). |
| `dataset.json` | Üretilen veri seti (çıktı, `.gitignore`'da). |
| `skip.txt` | Atlanacak "zehirli" video ID'leri (otomatik doldurulur). |

---

## 📦 Çıktı şeması (`dataset.json`)

Her kayıt:

```json
{
  "video_id": "YouTube_Video_ID",
  "raw_transcript": "Temizlenmiş + LaTeX'e çevrilmiş metin",
  "cot_steps": ["Adım adım çözüm cümleleri (LaTeX formatlı)"],
  "processed_at": "2026-06-25T20:43:00"
}
```

- **Idempotent:** `dataset.json`'da `video_id` zaten varsa video atlanır, veri **ezilmez**, sona **eklenir**.
- **Resumable:** Kesinti/çökme sonrası kaldığı yerden devam eder.
- **Crash-safe:** Her kayıttan sonra dosya atomik (`.tmp` → `replace`) yazılır.

---

## 🪄 Temizlik & LaTeX sihirbazı (`cleaner.py`)

**Ayıklanan kalıplar:** "kanala abone olun", "beğenmeyi unutmayın", "hepinize merhaba arkadaşlar", "bir sonraki videoda görüşmek üzere", sosyal medya çağrıları vb. (içeren cümleler tamamen düşer).

**Konuşma dili → LaTeX dönüşümleri** (Türkçe büyük/küçük harfe duyarlı):

| Konuşma | LaTeX |
|---|---|
| kök üç | `$\sqrt{3}$` |
| x kare | `$x^2$` |
| x küp | `$x^3$` |
| x üzeri dört | `$x^{4}$` |
| a bölü iki | `$a/2$` |
| üç çarpı dört | `$3 \times 4$` |
| doksan derece | `$90^\circ$` |
| ABC üçgeninin alanı | `$A(\triangle ABC)$` |
| pi sayısı | `$\pi$` |

Doğrulamak için: `python test_cleaner.py` (23/23 test geçer).

---

## ⚙️ Ayarlar (opsiyonel ortam değişkenleri)

| Değişken | Varsayılan | Açıklama |
|---|---|---|
| `WHISPER_MODEL` | `large-v3` | Model adı (örn. `medium` daha hızlı). |
| `WHISPER_DEVICE` | otomatik | `cuda` / `cpu` zorla. |
| `WHISPER_COMPUTE_TYPE` | otomatik | `float16` / `int8` zorla. |
| `WHISPER_BEAM` | `5` | Beam size (doğruluk/hız dengesi). |

---

## ⚠️ Notlar

- `ffmpeg` bir pip paketi değildir; sistem bağımlılığıdır. `run.ps1`/`run.sh` kontrol edip yönlendirir.
- `dataset.json`, ses ve loglar `.gitignore` ile repoya dâhil edilmez (büyük olabilir + telif). Veriyi de sürümlemek istersen `.gitignore`'daki `dataset.json` satırını kaldır veya [Git LFS](https://git-lfs.com/) kullan.
- Eski bir `dataset.json`'un varsa (farklı şemada): yeni şema `video_id` anahtarına göre idempotency uygular. Eski dosyada `video_id` alanı yoksa kayıtlar yeniden işlenebilir; temiz başlangıç için eski dosyayı yedekleyip kaldırman önerilir.
