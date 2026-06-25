# -*- coding: utf-8 -*-
"""
cleaner.py — Türkçe ham transcript temizleme + LaTeX dönüşüm sihirbazı.

Saf Python; harici bağımlılığı yoktur, bu yüzden bağımsız test edilebilir.
Genel akış:  clean_transcript(raw) -> strip_promos -> to_latex -> normalize
"""
import re

__all__ = ["clean_transcript", "to_latex", "strip_promos", "split_steps", "tr_lower"]


# --------------------------------------------------------------------------- #
# Türkçe'ye duyarlı küçük harf (I/İ ve ı/i ikilemi regex'i bozmasın diye)
# --------------------------------------------------------------------------- #
def tr_lower(s: str) -> str:
    return s.replace("I", "ı").replace("İ", "i").lower()


# --------------------------------------------------------------------------- #
# Sayı sözcükleri (rakama çevirmek için). ASCII varyasyonları da eklendi,
# çünkü Whisper bazen aksansız ("uc", "bes") yazabiliyor.
# --------------------------------------------------------------------------- #
_NUM = {
    "sıfır": "0", "sifir": "0", "bir": "1", "iki": "2", "üç": "3", "uc": "3",
    "dört": "4", "dort": "4", "beş": "5", "bes": "5", "altı": "6", "alti": "6",
    "yedi": "7", "sekiz": "8", "dokuz": "9", "on": "10", "yirmi": "20",
    "otuz": "30", "kırk": "40", "kirk": "40", "elli": "50", "altmış": "60",
    "altmis": "60", "yetmiş": "70", "yetmis": "70", "seksen": "80",
    "doksan": "90", "yüz": "100", "yuz": "100", "bin": "1000",
}
# Uzun olanı önce dene (greedy eşleşme için)
_NUM_RE = "(?:" + "|".join(sorted(map(re.escape, _NUM), key=len, reverse=True)) + ")"

# operand: rakam | sayı-sözcüğü | tek latin harf (değişken: x, y, a ...).
# Tek harf değişkenin başka harfe yapışmaması için ileri-bakış kullanıyoruz.
_OP = r"(\d+|" + _NUM_RE + r"|[a-zA-Z](?![a-zA-Z]))"

_F = re.IGNORECASE | re.UNICODE


def _op(tok: str) -> str:
    """Operandı LaTeX gövdesine çevir (sayı sözcüğü -> rakam, diğerleri aynen)."""
    return _NUM.get(tr_lower(tok), tok)


# --------------------------------------------------------------------------- #
# LaTeX dönüşüm kuralları. Sıra önemlidir: özel olan önce gelir.
# Her kural eşleştiği parçayı $...$ içine alır.
# --------------------------------------------------------------------------- #
_RULES = []


def _rule(pattern: str, fn):
    _RULES.append((re.compile(pattern, _F), fn))


# --- Karekök / kök ---
_rule(r"\bkare\s*kök\s+" + _OP, lambda m: "$\\sqrt{" + _op(m.group(1)) + "}$")
_rule(r"\bkök\s+içinde\s+" + _OP, lambda m: "$\\sqrt{" + _op(m.group(1)) + "}$")
_rule(r"\bkök\s+" + _OP, lambda m: "$\\sqrt{" + _op(m.group(1)) + "}$")

# --- Üs alma ---
_rule(_OP + r"\s+üzeri\s+" + _OP,
      lambda m: "$" + _op(m.group(1)) + "^{" + _op(m.group(2)) + "}$")
_rule(_OP + r"\s+kare\b", lambda m: "$" + _op(m.group(1)) + "^2$")
_rule(_OP + r"\s+küp\b", lambda m: "$" + _op(m.group(1)) + "^3$")

# --- Bölme (iki operandlı ve tek operandlı) ---
_rule(_OP + r"\s+bölü\s+" + _OP,
      lambda m: "$" + _op(m.group(1)) + "/" + _op(m.group(2)) + "$")
_rule(r"\bbölü\s+" + _OP, lambda m: "$/" + _op(m.group(1)) + "$")

# --- Dört işlem / eşitlik ---
_rule(_OP + r"\s+çarpı\s+" + _OP,
      lambda m: "$" + _op(m.group(1)) + " \\times " + _op(m.group(2)) + "$")
_rule(_OP + r"\s+artı\s+" + _OP,
      lambda m: "$" + _op(m.group(1)) + " + " + _op(m.group(2)) + "$")
_rule(_OP + r"\s+eksi\s+" + _OP,
      lambda m: "$" + _op(m.group(1)) + " - " + _op(m.group(2)) + "$")
_rule(_OP + r"\s+eşittir\s+" + _OP,
      lambda m: "$" + _op(m.group(1)) + " = " + _op(m.group(2)) + "$")

# --- Açı / derece ---
_rule(_OP + r"\s+derece\b", lambda m: "$" + _op(m.group(1)) + "^\\circ$")

# --- Geometri (üçgen) ---
_rule(r"\b([A-Z]{2,4})\s+üçgeninin\s+alanı",
      lambda m: "$A(\\triangle " + m.group(1) + ")$")
_rule(r"\büçgenin\s+alanı", lambda m: "$A(\\triangle)$")
_rule(r"\b([A-Z]{2,4})\s+üçgeni\b", lambda m: "$\\triangle " + m.group(1) + "$")
_rule(r"\büçgen\s+([A-Z]{2,4})\b", lambda m: "$\\triangle " + m.group(1) + "$")

# --- Yunan harfleri / sabitler ---
_rule(r"\bpi\s+sayısı\b", lambda m: "$\\pi$")


def to_latex(text: str) -> str:
    """Konuşma dilindeki matematiği $...$ LaTeX'e çevirir."""
    for rx, fn in _RULES:
        text = rx.sub(fn, text)
    # Yan yana gelen $...$ $...$ parçalarındaki gereksiz boşluğu sadeleştir
    text = re.sub(r"\$\s+\$", " ", text)
    return text


# --------------------------------------------------------------------------- #
# Reklam / giriş / kapanış / sosyal medya kalıplarını ayıklama
# --------------------------------------------------------------------------- #
_PROMO = [
    r"abone\s+ol",
    r"beğen\w*\s+unut",
    r"beğen\w*\s+atma",
    r"like\s+at",
    r"zil\w*\s+aç",
    r"bildirim\w*\s+aç",
    r"yorum\w*\s+(yaz|at|bırak)",
    r"kanal\w*\s+(abone|destek|takip)",
    r"kanalım\w*",
    r"bir\s+sonraki\s+video",
    r"görüşmek\s+üzere",
    r"hepinize\s+merhaba",
    r"merhaba\s+arkadaşlar",
    r"selam\w*\s+arkadaşlar",
    r"hoş\s+geldin\w*",
    r"iyi\s+seyirler",
    r"iyi\s+dersler",
    r"destek\s+ol\w*",
    r"paylaş\w*\s+unut",
    r"takip\s+et\w*",
    r"sosyal\s+medya",
    r"instagram",
    r"telegram",
]
_PROMO_RX = [re.compile(p, _F) for p in _PROMO]

# Cümle sınırlarına bölmek için (.!? sonrası boşluk)
_SENT_SPLIT = re.compile(r"(?<=[.!?…])\s+")


def strip_promos(text: str) -> str:
    """Reklam/giriş/kapanış içeren cümleleri tamamen düşürür."""
    sentences = _SENT_SPLIT.split(text)
    kept = [s for s in sentences if not any(rx.search(s) for rx in _PROMO_RX)]
    out = " ".join(kept)
    return re.sub(r"\s{2,}", " ", out).strip()


# --------------------------------------------------------------------------- #
# Tam temizlik hattı
# --------------------------------------------------------------------------- #
def clean_transcript(raw: str) -> str:
    """Whisper çıktısını temizleyip LaTeX'e çevrilmiş düz metin döndürür."""
    t = (raw or "").strip()
    t = re.sub(r"\s+", " ", t)        # boşlukları normalize et
    t = strip_promos(t)              # reklam/giriş/kapanış ayıkla
    t = to_latex(t)                  # matematiği LaTeX'e çevir
    t = re.sub(r"\s{2,}", " ", t).strip()
    return t


def split_steps(cleaned: str) -> list:
    """Temizlenmiş metni adım adım (cümle bazlı) çözüm adımlarına böler."""
    parts = _SENT_SPLIT.split(cleaned)
    return [p.strip() for p in parts if len(p.strip()) > 2]


# Doğrudan çalıştırılırsa kısa bir demo göster
if __name__ == "__main__":
    demo = ("Hepinize merhaba arkadaşlar, kanala abone olmayı unutmayın. "
            "Şimdi x kare artı iki eşittir on bir. Kök üç bölü iki alıyoruz. "
            "ABC üçgeninin alanı doksan derece. Bir sonraki videoda görüşmek üzere.")
    print(clean_transcript(demo))
