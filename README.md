# YKS Soru Çözümü — Deşifre & Dataset Pipeline

YKS soru-çözüm videolarını YouTube'dan toplu olarak indirip [Whisper](https://github.com/openai/whisper) ile **deşifre eden** (transcribe) ve yapılandırılmış bir `dataset.json` üreten pipeline. Üretilen veri, sonraki adımda bir LLM ile temizlenip soru-çözüm veri setine dönüştürülür.

## Nasıl çalışır

1. **İndirme** — `yt-dlp` ile her videonun sesi indirilir.
2. **Deşifre** — `faster-whisper` (ctranslate2 / CUDA) ile ses metne çevrilir.
   - Modeller: kalite kontrolü için ilk birkaç videoda `large-v3`, gerisinde hız için `medium`.
3. **Kayıt** — Her video bir kayıt olarak `dataset.json`'a eklenir. Süreç **resumable**'dır: kaldığı yerden devam eder.
4. **Temizleme (sonraki aşama)** — Transcript'ler bir LLM ile temizlenip son veri setine dönüştürülür.

## Dosya yapısı

| Dosya | Açıklama |
|---|---|
| `pipeline.py` | Deşifre pipeline'ı; `skip.txt` desteğiyle sorunlu ("zehirli") videoları atlar. |
| `run_all.ps1` | Orkestrasyon + **otomatik kurtarma** döngüsü (Windows / PowerShell). |
| `dataset.json` | Üretilen veri seti (her video bir kayıt). |
| `skip.txt` | Atlanacak / çökmeye yol açan video ID'leri. |
| `run_all.log` | Çalışma logları. |

## Kullanım (Windows / PowerShell)

```powershell
cd "C:\Users\ASUS\Desktop\YUSA\YKS SORULARI"
./run_all.ps1
```

Canlı log izleme:

```powershell
Get-Content run_all.log -Tail 20 -Wait -Encoding UTF8
```

## Otomatik kurtarma (auto-recovery)

`run_all.ps1` bir döngü içinde çalışır ve dayanıklıdır:

- Pipeline çökerse **kendini yeniden başlatır** ve kaldığı yerden devam eder (resumable).
- Yeniden başlatmaya rağmen **ilerleme olmuyorsa**, son işlenen ("zehirli") videoyu `skip.txt`'e ekleyip atlar.
- **Üst üste 3 kez** kurtaramazsa durur ve haber verir.

> Bu mekanizma, video 554'te (`9nHnUnQ5BJQ`) yaşanan native çökmeden sonra eklendi (çıkış kodu `0xC0000409`, ctranslate2/CUDA tarafı). O olayda eski script sessizce durmuş ve ~7.5 saat kaybedilmişti; artık benzer durumda pipeline kendini onarır.

## Durum (son güncelleme)

- İşlenen: ~772 / 1309 kayıt (~%59)
- Ortalama: ~2.7 dk/video
- Tahmini kalan: deşifre ~17–18 saat, ardından LLM temizleme ~1–1.5 gün

## Notlar

- `dataset.json`, ses ve log dosyaları `.gitignore` ile repoya dâhil **edilmez** (büyük olabilir ve YouTube içeriği barındırır).
- Veriyi de sürümlemek istersen `.gitignore` içindeki `dataset.json` satırını kaldır veya büyük dosyalar için [Git LFS](https://git-lfs.com/) kullan.
