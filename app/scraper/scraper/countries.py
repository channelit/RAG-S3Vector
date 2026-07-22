"""Country detection for CSMS subjects/bodies.

Curated for trade-message vocabulary. Each entry is (canonical name,
case-insensitive pattern, case-sensitive pattern) — the case-sensitive slot
holds acronyms and ambiguous words (e.g. "Turkey" the country vs "turkey"
poultry). "United States" is deliberately excluded: every CSMS message is
US-related, so it carries no filtering signal. "Georgia" is excluded because
it collides with the U.S. state in port names.
"""

import re

_RAW: list[tuple[str, str | None, str | None]] = [
    ("China", r"china|chinese|people'?s republic of china", r"\bPRC\b"),
    ("Hong Kong", r"hong\s?kong", None),
    ("Macau", r"maca[uo]", None),
    ("Taiwan", r"taiwan", None),
    ("Japan", r"japan|japanese", None),
    ("South Korea", r"south korea|republic of korea|korean?(?!\s+war)", r"\bROK\b"),
    ("North Korea", r"north korea", r"\bDPRK\b"),
    ("India", r"india(?!n)", None),
    ("Pakistan", r"pakistan", None),
    ("Bangladesh", r"bangladesh", None),
    ("Sri Lanka", r"sri lanka", None),
    ("Nepal", r"\bnepal", None),
    ("Vietnam", r"viet\s?nam|vietnamese", None),
    ("Thailand", r"thailand|\bthai\b", None),
    ("Cambodia", r"cambodia", None),
    ("Laos", r"\blaos?\b", None),
    ("Myanmar", r"myanmar|burma|burmese", None),
    ("Malaysia", r"malaysia", None),
    ("Singapore", r"singapore", None),
    ("Indonesia", r"indonesia", None),
    ("Philippines", r"philippine", None),
    ("Australia", r"australia", None),
    ("New Zealand", r"new zealand", None),
    ("Russia", r"russia|russian federation|russian", None),
    ("Ukraine", r"ukrain", None),
    ("Belarus", r"belarus", None),
    ("Kazakhstan", r"kazakhstan", None),
    ("Uzbekistan", r"uzbekistan", None),
    ("European Union", r"european union", r"\bEU\b"),
    ("Germany", r"german", None),
    ("France", r"\bfrance|french\b", None),
    ("Italy", r"\bitaly|italian", None),
    ("Spain", r"\bspain|spanish", None),
    ("Portugal", r"portug", None),
    ("Netherlands", r"netherlands|\bdutch\b", None),
    ("Belgium", r"belgi", None),
    ("Luxembourg", r"luxembourg", None),
    ("Austria", r"austria", None),
    ("Switzerland", r"switzerland|\bswiss\b", None),
    ("United Kingdom", r"united kingdom|great britain|\bbritain|british", r"\bUK\b"),
    ("Ireland", r"\bireland|\birish\b", None),
    ("Sweden", r"\bsweden|swedish", None),
    ("Norway", r"\bnorway|norwegian", None),
    ("Denmark", r"denmark|danish", None),
    ("Finland", r"finland|finnish", None),
    ("Iceland", r"iceland", None),
    ("Poland", r"\bpoland|polish\b", None),
    ("Czechia", r"czech", None),
    ("Slovakia", r"slovak", None),
    ("Hungary", r"hungar", None),
    ("Romania", r"romania", None),
    ("Bulgaria", r"bulgaria", None),
    ("Greece", r"\bgreece|greek\b", None),
    ("Turkey", r"t[üu]rkiye", r"\bTurkey\b|\bTurkish\b"),
    ("Israel", r"israel", None),
    ("Jordan", None, r"\bJordan(?:ian)?\b"),
    ("Egypt", r"egypt", None),
    ("Morocco", r"morocc", None),
    ("Tunisia", r"tunisia", None),
    ("Algeria", r"algeria", None),
    ("Libya", r"libya", None),
    ("Saudi Arabia", r"saudi", None),
    ("United Arab Emirates", r"united arab emirates|emirati", r"\bUAE\b"),
    ("Qatar", r"qatar", None),
    ("Kuwait", r"kuwait", None),
    ("Bahrain", r"bahrain", None),
    ("Oman", r"\boman\b|omani", None),
    ("Yemen", r"yemen", None),
    ("Iran", r"\biran\b|iranian", None),
    ("Iraq", r"\biraq\b|iraqi", None),
    ("Syria", r"\bsyria\b|syrian", None),
    ("Lebanon", r"lebanon|lebanese", None),
    ("Afghanistan", r"afghan", None),
    ("Mexico", r"mexic", None),
    ("Canada", r"canad", None),
    ("Brazil", r"brazil", None),
    ("Argentina", r"argentin", None),
    ("Chile", r"\bchile\b|chilean", None),
    ("Peru", r"\bperu\b|peruvian", None),
    ("Colombia", r"colombia", None),
    ("Venezuela", r"venezuela", None),
    ("Ecuador", r"ecuador", None),
    ("Bolivia", r"bolivia", None),
    ("Uruguay", r"uruguay", None),
    ("Paraguay", r"paraguay", None),
    ("Panama", r"panama", None),
    ("Costa Rica", r"costa rica", None),
    ("Nicaragua", r"nicaragua", None),
    ("Honduras", r"honduras", None),
    ("Guatemala", r"guatemala", None),
    ("El Salvador", r"el salvador", None),
    ("Dominican Republic", r"dominican republic", None),
    ("Haiti", r"\bhaiti", None),
    ("Cuba", r"\bcuban?\b", None),
    ("Jamaica", r"jamaica", None),
    ("Bahamas", r"bahamas", None),
    ("Trinidad and Tobago", r"trinidad", None),
    ("South Africa", r"south africa", None),
    ("Nigeria", r"nigeria", None),
    ("Kenya", r"kenya", None),
    ("Ethiopia", r"ethiopia", None),
    ("Ghana", r"\bghana", None),
    ("Madagascar", r"madagascar", None),
    ("Chad", None, r"\bChad\b"),
    ("Niger", None, r"\bNiger\b"),
    ("Guinea", None, r"\bGuinea\b"),
]

_COMPILED: list[tuple[str, re.Pattern | None, re.Pattern | None]] = [
    (
        name,
        re.compile(rf"\b(?:{ci})\b", re.IGNORECASE) if ci else None,
        re.compile(cs) if cs else None,
    )
    for name, ci, cs in _RAW
]


def detect_countries(*texts: str, body_scan_limit: int = 20_000) -> list[str]:
    """Return canonical country names mentioned in the given texts.

    Order: first occurrence across the concatenated input (so subject hits,
    passed first, lead the list).
    """
    corpus = "\n".join(t[:body_scan_limit] for t in texts if t)
    found: list[tuple[int, str]] = []
    for name, ci, cs in _COMPILED:
        pos: int | None = None
        for pattern in (ci, cs):
            if pattern is None:
                continue
            m = pattern.search(corpus)
            if m and (pos is None or m.start() < pos):
                pos = m.start()
        if pos is not None:
            found.append((pos, name))
    return [name for _, name in sorted(found)]
