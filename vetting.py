"""Offline name vetting: memorability, trademark strength, and a conflict
screen against well-known fashion brands. Heuristics only — not legal advice."""
import re

# Well-known fashion / apparel / accessories / beauty brands (Classes 3, 14, 18, 25, 35).
FAMOUS = """
nike adidas puma reebok asics newbalance underarmour lululemon gymshark fila converse vans
gucci prada chanel dior louisvuitton hermes versace armani fendi balenciaga givenchy valentino
burberry celine loewe bottegaveneta saintlaurent ysl alexandermcqueen moncler moschino miumiu
dolcegabbana balmain kenzo jacquemus offwhite stoneisland acnestudios maisonmargiela marni
coach michaelkors katespade toryburch ralphlauren polo tommyhilfiger calvinklein hugoboss
lacoste guess diesel levis wrangler lee gap oldnavy bananarepublic jcrew abercrombie hollister
americaneagle aerie zara hm uniqlo mango cos arket stories primark shein fashionnova boohoo
prettylittlething asos topshop forever21 urbanoutfitters anthropologie freepeople madewell
everlane reformation aritzia skims fenty savagexfenty victoriassecret aerie spanx
patagonia thenorthface columbia carhartt dickies timberland drmartens ugg crocs birkenstock
supreme stussy palace kith bape fearofgod essentials aimeleondore rhude amiri represent
corteiz trapstar golfwang chromehearts vetements rickowens yohjiyamamoto commedesgarcons
isseymiyake sacai undercover neighborhood wtaps visvim kapital
tiffany cartier bulgari pandora swarovski chopard rolex omega
sephora glossier rarebeauty kyliecosmetics maccosmetics nars clinique esteelauder
champion hanes fruitoftheloom jockey superdry ellesse kappa umbro diadora mizuno onrunning hoka
salomon arcteryx canadagoose barbour belstaff allsaints tedbaker sandro maje zadig
rag ragandbone theory vince alo aloyoga vuori outdoorvoices fabletics sweatybetty
""".split()

GENERIC = set("""
clothing clothes apparel fashion wear garments outfit outfits dress dresses shirt shirts tee tees
tshirt hoodie hoodies jeans denim shoes sneakers boutique store shop style styles
""".split())

DESCRIPTIVE = set("""
threads couture studio label collective co company brand designs design goods supply
luxe luxury urban street streetwear athletic active sport sports fit wardrobe closet
chic vintage modern classic basics essentials premium cozy comfy soft cotton silk linen
lux elite trendy glam
""".split())

VOWELS = set("aeiouy")


def slug(s):
    return re.sub(r"[^a-z0-9]", "", s.lower())


def levenshtein(a, b):
    if a == b:
        return 0
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def phonetic(s):
    """Lightweight sound-alike key (handles ph/f, c/k, z/s, doubled letters, silent vowels)."""
    s = slug(s)
    for a, b in (("ph", "f"), ("ck", "k"), ("qu", "kw"), ("x", "ks"), ("c", "k"),
                 ("z", "s"), ("y", "i"), ("w", "v"), ("gh", "g"), ("kn", "n")):
        s = s.replace(a, b)
    s = re.sub(r"(.)\1+", r"\1", s)
    if s:
        s = s[0] + re.sub(r"[aeiou]", "", s[1:])
    return s


def syllables(word):
    w = word.lower()
    groups = re.findall(r"[aeiouy]+", w)
    n = len(groups)
    if w.endswith("e") and n > 1 and not w.endswith(("le", "ee")):
        n -= 1
    return max(1, n)


def _core(name):
    words = re.findall(r"[a-z0-9]+", name.lower())
    kept = [w for w in words if w not in GENERIC and w not in DESCRIPTIVE and w not in ("the", "by", "and", "of")]
    return "".join(kept) or slug(name)


def _compare(s, brand):
    """Return (reason, severity) or None for candidate slug s vs famous brand."""
    p, pb = phonetic(s), phonetic(brand)
    d = levenshtein(s, brand)
    if s == brand:
        return "Identical to a famous mark", "high"
    if p == pb and len(pb) >= 2:
        return "Sounds like a famous mark", "high"
    if len(brand) >= 4 and brand in s:
        return "Contains a famous mark", "high"
    if len(pb) >= 4 and pb in p:
        return "Contains a sound-alike of a famous mark", "high"
    if d <= (1 if len(brand) <= 5 else 2):
        return f"{d} letter{'s' if d > 1 else ''} away from a famous mark", "high"
    if len(s) >= 4 and s in brand:
        return "Is part of a famous mark", "medium"
    if levenshtein(p, pb) <= 1 and len(pb) >= 4:
        return "Sounds similar to a famous mark", "medium"
    if len(s) >= 5 and len(brand) >= 5 and s[:4] == brand[:4]:
        return "Starts like a famous mark", "medium"
    return None


def conflicts(name):
    full, core = slug(name), _core(name)
    hits = {}
    for brand in FAMOUS:
        if len(brand) < 3:
            continue
        for cand in {full, core}:
            r = _compare(cand, brand)
            if r and (brand not in hits or (r[1] == "high" and hits[brand]["severity"] != "high")):
                hits[brand] = {"brand": brand, "reason": r[0], "severity": r[1]}
    order = {"high": 0, "medium": 1}
    return sorted(hits.values(), key=lambda h: order[h["severity"]])[:8]


def strength(name):
    words = re.findall(r"[a-z0-9]+", name.lower())
    s = slug(name)
    generic = [w for w in words if w in GENERIC]
    descr = [w for w in words if w in DESCRIPTIVE]
    if words and all(w in GENERIC for w in words):
        return {"level": "generic", "score": 0,
                "note": "Entirely generic for clothing — cannot be registered as a trademark."}
    if words and all(w in GENERIC or w in DESCRIPTIVE for w in words):
        return {"level": "descriptive", "score": 30,
                "note": "Describes the goods. USPTO will likely refuse without proof of acquired distinctiveness."}
    if generic or descr:
        return {"level": "suggestive", "score": 65,
                "note": f"Distinctive core, but '{', '.join(generic + descr)}' is weak — you'll likely have to disclaim it, and protection rests on the rest of the name."}
    if re.fullmatch(r"[a-z]+", s) and len(s) >= 4 and not any(v in s for v in VOWELS):
        return {"level": "arbitrary", "score": 80, "note": "Letter-string mark; registrable but harder to protect and remember."}
    return {"level": "coined/arbitrary", "score": 95,
            "note": "No obvious descriptive words — the strongest category for trademark protection (verify it isn't a real word that describes clothing)."}


def memorability(name):
    s = slug(name)
    words = re.findall(r"[a-zA-Z]+", name)
    syl = sum(syllables(w) for w in words) or 1
    notes = []
    score = 100
    if len(s) > 14:
        score -= 30; notes.append("Long — harder to fit in a handle or logo.")
    elif len(s) > 10:
        score -= 12; notes.append("On the long side for a handle.")
    elif len(s) < 3:
        score -= 25; notes.append("Very short — premium domains/handles almost certainly gone.")
    if syl > 4:
        score -= 15; notes.append(f"{syl} syllables — 1–3 is easiest to say.")
    if re.search(r"[bcdfghjklmnpqrstvwxz]{4,}", s):
        score -= 20; notes.append("Hard consonant cluster — may be hard to pronounce.")
    if re.search(r"\d", s):
        score -= 10; notes.append("Numbers create 'spelled-out vs digit' confusion.")
    if re.search(r"[-_.]", name):
        score -= 10; notes.append("Punctuation rarely survives in handles or domains.")
    if re.search(r"(ph|ck|ie$|ee|ou|kk|zz|xx)", s) or re.search(r"(.)\1\1", s):
        score -= 5; notes.append("Spelling may be ambiguous when heard aloud.")
    if s.endswith("s") and len(s) > 4:
        notes.append("Ends in 's' — someone may already own the singular.")
    if not notes:
        notes.append("Short, pronounceable, easy to spell.")
    return {"score": max(0, score), "syllables": syl, "length": len(s), "notes": notes}


CLASSES = [
    {"cls": 25, "label": "Clothing, footwear, headwear", "core": True},
    {"cls": 35, "label": "Online/retail store services", "core": True},
    {"cls": 18, "label": "Bags, wallets, leather goods", "core": False},
    {"cls": 14, "label": "Jewelry, watches", "core": False},
    {"cls": 3, "label": "Cosmetics, fragrance", "core": False},
    {"cls": 9, "label": "Eyewear / sunglasses", "core": False},
]


def vet_name(name):
    conf = conflicts(name)
    st = strength(name)
    mem = memorability(name)
    risk = 0 if any(c["severity"] == "high" for c in conf) else (60 if conf else 100)
    overall = round(0.45 * st["score"] + 0.25 * mem["score"] + 0.30 * risk)
    if risk == 0 or st["level"] == "generic":
        overall = min(overall, 25)
    elif st["level"] == "descriptive":
        overall = min(overall, 40)
    return {"overall": overall, "strength": st, "memorability": mem,
            "conflicts": conf, "classes": CLASSES}
