# -*- coding: utf-8 -*-
"""cleaner.py için hızlı doğrulama testleri (harici bağımlılık yok)."""
from cleaner import clean_transcript, to_latex, strip_promos, split_steps

cases = []


def check(name, got, expect_in):
    ok = expect_in in got
    cases.append(ok)
    flag = "✓" if ok else "✗"
    print(f"{flag} {name}\n    beklenen içerir: {expect_in!r}\n    sonuç          : {got!r}")


# --- LaTeX dönüşümleri ---
check("kök üç",            to_latex("kök üç"),            "$\\sqrt{3}$")
check("karekök beş",       to_latex("karekök beş"),       "$\\sqrt{5}$")
check("kök x",             to_latex("kök x"),             "$\\sqrt{x}$")
check("x kare",            to_latex("x kare"),            "$x^2$")
check("üç kare",           to_latex("üç kare"),           "$3^2$")
check("x küp",             to_latex("x küp"),             "$x^3$")
check("x üzeri dört",      to_latex("x üzeri dört"),      "$x^{4}$")
check("a bölü iki",        to_latex("a bölü iki"),        "$a/2$")
check("bölü iki (tek)",    to_latex("bölü iki"),          "$/2$")
check("üç çarpı dört",     to_latex("üç çarpı dört"),     "$3 \\times 4$")
check("doksan derece",     to_latex("doksan derece"),     "$90^\\circ$")
check("ABC üçgeninin alanı", to_latex("ABC üçgeninin alanı"), "$A(\\triangle ABC)$")
check("üçgen ABC",         to_latex("üçgen ABC"),         "$\\triangle ABC$")
check("pi sayısı",         to_latex("pi sayısı"),         "$\\pi$")

# --- Büyük/küçük harf varyasyonu (Türkçe) ---
check("KÖK ÜÇ (büyük)",    to_latex("KÖK ÜÇ"),            "$\\sqrt{3}$")

# --- Reklam/giriş/kapanış ayıklama ---
promo = ("Hepinize merhaba arkadaşlar. Kanala abone olmayı unutmayın. "
         "x kare eşittir dört. Bir sonraki videoda görüşmek üzere.")
cleaned = strip_promos(promo)
check("promo: merhaba düştü", cleaned, "")  # placeholder, asıl kontrol altta
print("    [strip_promos] ->", repr(cleaned))
cases.append("merhaba" not in cleaned.lower())
cases.append("abone" not in cleaned.lower())
cases.append("sonraki video" not in cleaned.lower())
cases.append("x kare" in cleaned)

# --- Uçtan uca ---
e2e = clean_transcript(promo)
print("    [clean_transcript] ->", repr(e2e))
cases.append("$x^2$" in e2e)
cases.append("abone" not in e2e.lower())

# --- Adımlara bölme ---
steps = split_steps("Önce $x^2$ buluyoruz. Sonra $\\sqrt{3}$ alıyoruz. Sonuç hazır.")
print("    [split_steps] ->", steps)
cases.append(len(steps) == 3)

print("\n" + "=" * 50)
passed = sum(1 for c in cases if c)
print(f"SONUÇ: {passed}/{len(cases)} test geçti")
raise SystemExit(0 if passed == len(cases) else 1)
