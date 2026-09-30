"""Оценка риска аккаунта: категория сервиса, признаки покупок и утечки.

Риск считается при каждом показе (а не при импорте почты), поэтому обновлённые
справочники категорий и список утечек применяются без повторного анализа архива.
"""

from __future__ import annotations

import json
import re
from functools import lru_cache

from . import RESOURCES_DIR, breaches
from .signals import LIKELY, NEWSLETTER, PERSONAL, SURE, service_domain

HIGH, MEDIUM, LOW = "high", "medium", "low"
LEVEL_ORDER = {HIGH: 0, MEDIUM: 1, LOW: 2}

# Категория → (название, базовый риск).
CATEGORIES: dict[str, tuple[str, str]] = {
    "finance": ("Финансы", HIGH),
    "shop": ("Магазин", HIGH),
    "delivery": ("Доставка", HIGH),
    "taxi": ("Такси", HIGH),
    "tickets": ("Билеты и поездки", HIGH),
    "gov": ("Госуслуги", HIGH),
    "medical": ("Медицина", HIGH),
    "social": ("Соцсеть", HIGH),
    "jobs": ("Вакансии", HIGH),
    "dating": ("Знакомства", HIGH),
    "other": ("Сервис", MEDIUM),
    "newsletter": ("Рассылка", LOW),
    "news": ("Новости", LOW),
    "blog": ("Блог", LOW),
}
HIGH_CATEGORIES = [c for c, (_, lvl) in CATEGORIES.items() if lvl == HIGH]

# Темы писем → категория. Проверяются в этом порядке; «низкие» категории — последними,
# чтобы магазин с рекламной рассылкой оставался магазином.
TOPIC_PATTERNS: dict[str, list[str]] = {
    "finance": [
        r"\bбанк", r"выписк", r"перевод\w* (?:средств|денег|на карту|с карты)", r"списани", r"зачислени",
        r"\bкредит", r"\bвклад", r"кэшб[еэ]к", r"(?:дебетов|кредитн|банковск)\w* карт", r"транзакци",
        r"инвестиц", r"брокерск", r"\bкошел[её]к",
        r"\bbank", r"(?:account|bank|card|monthly) statement", r"\btransaction", r"money transfer",
        r"\bwithdraw", r"\bdeposit", r"\bloan\b", r"credit card", r"debit card", r"\bwallet\b", r"\bcrypto",
        r"\bbitcoin",
    ],
    "delivery": [
        r"доставк", r"курьер", r"посылк", r"отправлени\w* (?:прибыл|получ|№)", r"трек-?номер",
        r"пункт\w* выдачи", r"постамат", r"\bпередан\w* в службу",
        r"\bshipped\b", r"\bshipping\b", r"\bdelivery\b", r"\bcourier\b", r"\bparcel\b",
        r"\btracking (?:number|info)", r"out for delivery",
    ],
    "taxi": [
        r"\bтакси", r"\bпоездк", r"\bводител", r"\bride\b", r"\byour trip\b", r"\bdriver\b",
    ],
    "tickets": [
        r"\bбилет", r"бронировани", r"\bрейс", r"посадочн", r"\bотел[ья]", r"перел[её]т", r"маршрутн\w* квитанц",
        r"\be-?tickets?\b", r"\btickets? (?:for|to|are|confirm)", r"your tickets\b", r"\bbooking\b",
        r"\bflight", r"boarding pass", r"\bhotel", r"\breservation", r"\bitinerary", r"\bcheck-?in\b",
    ],
    "gov": [
        r"госуслуг", r"\bналог", r"\bфнс\b", r"\bпфр\b", r"\bсфр\b", r"\bгибдд\b", r"\bштраф",
        r"электронн\w* правительств", r"\bмфц\b",
        r"\btax (?:return|refund|notice)", r"\bgovernment\b", r"\bvisa application",
    ],
    "medical": [
        r"запис\w* (?:к|на при[её]м) (?:врач|специалист|доктор)", r"\bврач", r"\bклиник", r"результат\w* анализ",
        r"\bмедицин", r"\bаптек", r"\bрецепт", r"\bполис\w* (?:омс|дмс)", r"\bстоматолог", r"\bтелемедицин",
        r"\bdoctor\b", r"\bclinic\b", r"\bappointment\b", r"\bprescription", r"\bpharmacy", r"lab results",
        r"\bpatient\b", r"\bhealth (?:record|plan|insurance)",
    ],
    "social": [
        r"в друзья", r"друз\w* (?:добавил|приглаш|отметил|хочет)", r"подписчик", r"\bлайк", r"комментари",
        r"отметил\w* (?:вас|тебя)", r"упомянул", r"(?:новое|новые|личное) сообщени", r"\bзаписи? на стене",
        r"friend request", r"\bfollower", r"\bliked\b", r"\bcommented\b", r"\bmentioned you", r"\btagged you",
        r"new message", r"sent you a message",
    ],
    "jobs": [
        r"ваканси", r"\bрезюме", r"\bотклик", r"собеседовани", r"работодател", r"\bрекрутер",
        r"\bjob (?:alert|offer|opening|application)s?", r"\bnew jobs\b", r"\bjobs for you", r"\bvacanc",
        r"\bresume\b", r"\bcv\b", r"\binterview", r"\brecruiter", r"\bhiring\b", r"your application",
    ],
    "dating": [
        r"знакомств", r"симпати", r"\bанкет", r"\bвзаимн\w* (?:лайк|симпат)",
        r"new match", r"it'?s a match", r"\bdating\b", r"likes you", r"\bcrush\b",
    ],
    "shop": [
        r"\bкорзин", r"\bтовар", r"распродаж", r"\bартикул", r"оцените (?:товар|покупку)", r"\bснова в наличии",
        r"\bcart\b", r"\bwishlist\b", r"back in stock", r"\bon sale\b",
    ],
    "newsletter": [
        r"дайджест", r"\bподборк", r"\bрассылк", r"\bвыпуск\b", r"главное за", r"лучше\w* (?:статьи|за)",
        r"\bвебинар", r"\bнедел[иья]\b",
        r"\bdigest\b", r"\bnewsletter", r"\bweekly\b", r"this week", r"\broundup\b", r"what'?s new",
        r"\bwebinar",
    ],
    "news": [r"\bновост", r"\bnews\b", r"\bheadlines\b", r"\bbreaking\b", r"top stories"],
    "blog": [r"\bстать[яиюей]", r"\bблог", r"\bпост\b", r"\barticle", r"\bblog\b", r"\bpost\b", r"\bpodcast"],
}
_TOPICS = [(cat, re.compile("|".join(f"(?:{p})" for p in pats), re.IGNORECASE)) for cat, pats in TOPIC_PATTERNS.items()]

# Признаки покупок и заказов.
PURCHASE_PATTERNS = [
    r"\bзаказ", r"\bчек\b(?!-?лист)", r"электронн\w* чек", r"кассов\w* чек", r"\bоплат", r"\bоплач", r"\bплат[её]ж", r"квитанци",
    r"сч[её]т на оплату", r"сч[её]т[- ]фактур", r"\bпокупк", r"бронировани\w* подтвержд", r"\bоформлен",
    r"\border\b", r"\borders\b", r"\breceipt\b", r"\binvoice\b", r"\bpayment\b", r"\bpurchase\b",
    r"\bbilling\b", r"\bcharged\b", r"booking confirm", r"\bsubscription (?:renew|confirm)",
]
_PURCHASE = re.compile("|".join(f"(?:{p})" for p in PURCHASE_PATTERNS), re.IGNORECASE)

# Категория по словам в домене — если сервиса нет в справочнике.
DOMAIN_KEYWORDS: list[tuple[str, str]] = [
    ("finance", r"bank|banki|kredit|credit|zaim|loan|wallet|invest|broker|crypto|coin|capital|finance|insur|strah"),
    ("gov", r"gosuslug|nalog|^mos$"),
    ("medical", r"clinic|klinik|doctor|medic|med[a-z]*centr|apteka|pharm|dental|stomat|health|zdrav|lab(?:s|or)"),
    ("dating", r"dating|znakom|flirt|lovers?|tinder"),
    ("jobs", r"jobs?$|^jobs?|career|rabota|vacanc|resume|hiring|recruit|hunter"),
    ("taxi", r"taxi|^cab"),
    ("tickets", r"ticket|bilet|avia|airlines?|airways|hotel|travel|tours?$|kassa"),
    ("delivery", r"deliver|dostav|courier|kurier|express$|parcel|pochta"),
    ("shop", r"shop|store|market|mall|outlet|magazin|kupi|buy"),
    ("news", r"news|novosti|gazeta|times|herald|tribune|daily"),
    ("blog", r"blog"),
]
_DOMAIN_KEYWORDS = [(cat, re.compile(p)) for cat, p in DOMAIN_KEYWORDS]
GOV_SUFFIX_RE = re.compile(r"(?:^|\.)(?:gov|gouv|gob|mil)(?:\.[a-z]{2})?$|\.gov\.[a-z]{2,3}$")

BREACH_DATA_RU = {
    "Email addresses": "e-mail", "Passwords": "пароли", "Usernames": "логины", "Names": "имена",
    "Phone numbers": "телефоны", "Physical addresses": "адреса", "Dates of birth": "даты рождения",
    "IP addresses": "IP-адреса", "Credit cards": "банковские карты", "Partial credit card data": "данные карт",
    "Genders": "пол", "Geographic locations": "геолокация", "Purchases": "покупки",
    "Social media profiles": "профили соцсетей", "Private messages": "личные сообщения",
    "Security questions and answers": "контрольные вопросы", "Passport numbers": "паспорта",
    "Bank account numbers": "банковские счета", "Government issued IDs": "документы",
    "Auth tokens": "токены входа", "Device information": "устройства", "Payment histories": "история платежей",
    "Sexual orientations": "ориентация", "Health insurance information": "медстраховка",
    "Employers": "работодатели", "Job titles": "должности", "Salaries": "зарплаты",
}

# Веса оценки (0–100).
BASE_SCORE = {HIGH: 50, MEDIUM: 25, LOW: 5}
PURCHASE_SCORE = 20
BREACH_SCORE = 25          # утечка после первого письма от сервиса (или дата неизвестна)
OLD_BREACH_SCORE = 15      # утечка раньше, чем я, судя по письмам, пришёл в сервис
CONFIDENCE_SCORE = {SURE: 10, LIKELY: 5, NEWSLETTER: -10, PERSONAL: -20}
HIGH_FROM, MEDIUM_FROM = 55, 30

TOP_N = 30  # режим «Главное за 30 минут»


def subject_topics(subject: str) -> tuple[str, bool]:
    """Категория по теме письма ('' — не определена) и есть ли признак покупки."""
    if not subject:
        return "", False
    topic = next((cat for cat, rx in _TOPICS if rx.search(subject)), "")
    return topic, bool(_PURCHASE.search(subject))


def dominant_topic(counts: dict[str, int]) -> str:
    """Главная тема домена: высокорисковая, если такие письма вообще были, иначе самая частая."""
    high = {c: n for c, n in counts.items() if c in HIGH_CATEGORIES and n > 0}
    pool = high or {c: n for c, n in counts.items() if n > 0}
    if not pool:
        return ""
    return max(pool, key=lambda c: (pool[c], -list(TOPIC_PATTERNS).index(c)))


@lru_cache(maxsize=1)
def domain_categories() -> dict[str, str]:
    data = json.loads((RESOURCES_DIR / "categories.json").read_text(encoding="utf-8"))
    result: dict[str, str] = {}
    for cat, domains in data.items():
        if cat.startswith("_") or cat not in CATEGORIES:
            continue
        for d in domains:
            dom = service_domain(d) or d.lower()
            result.setdefault(dom, cat)
            result.setdefault(d.lower(), cat)
    return result


def category_for_domain(domain: str) -> str | None:
    domain = domain.lower()
    known = domain_categories().get(domain)
    if known:
        return known
    if GOV_SUFFIX_RE.search(domain):
        return "gov"
    label = domain.split(".")[0]
    for cat, rx in _DOMAIN_KEYWORDS:
        if rx.search(label):
            return cat
    return None


def resolve_category(domain: str, topic: str, confidence: str) -> tuple[str, str]:
    """Категория и откуда она взялась: 'domain', 'topic' или 'default'."""
    cat = category_for_domain(domain)
    if cat:
        return cat, "domain"
    if topic in CATEGORIES and (CATEGORIES[topic][1] == HIGH or confidence == NEWSLETTER):
        # «Низкая» тема (дайджест, новости) не делает безопасным сервис, где у меня есть аккаунт:
        # у Netflix тоже бывают подборки «на этой неделе».
        return topic, "topic"
    if confidence == NEWSLETTER:
        return "newsletter", "default"
    return "other", "default"


def level_for(score: int) -> str:
    if score >= HIGH_FROM:
        return HIGH
    if score >= MEDIUM_FROM:
        return MEDIUM
    return LOW


def assess(
    domain: str,
    *,
    topic: str = "",
    purchases: int = 0,
    confidence: str = LIKELY,
    first_day: str | None = None,
    index: breaches.BreachIndex | None = None,
) -> dict:
    index = index if index is not None else breaches.default_index()
    category, source = resolve_category(domain, topic, confidence)
    label, base_level = CATEGORIES[category]
    score = BASE_SCORE[base_level]
    reasons = [label.lower() if category != "other" else "обычный сервис"]

    if purchases > 0:
        score += PURCHASE_SCORE
        reasons.append("были покупки или заказы")

    found = index.match(domain)
    breached_after = False
    if found:
        # Утечка, случившаяся до первого письма от сервиса, меня, скорее всего, не задела.
        breached_after = not first_day or any(b.date >= first_day[:10] for b in found)
        score += BREACH_SCORE if breached_after else OLD_BREACH_SCORE
        latest = found[0]
        reasons.append(f"утечка {latest.date[:4]}" if latest.date else "утечка")

    score += CONFIDENCE_SCORE.get(confidence, 0)
    if confidence == NEWSLETTER:
        reasons.append("похоже, только рассылка")
    if breached_after:
        score = max(score, MEDIUM_FROM)  # утечка после моей регистрации — риск не ниже среднего
    score = max(0, min(100, score))

    return {
        "level": level_for(score),
        "score": score,
        "category": category,
        "category_label": label,
        "category_source": source,
        "purchases": purchases,
        "breached": bool(found),
        "breach_after_signup": breached_after,
        "breaches": [
            {**b.as_dict(), "data_ru": [BREACH_DATA_RU.get(c, c) for c in b.data_classes]}
            for b in found
        ],
        "reasons": reasons,
    }


def sort_key(s: dict) -> tuple:
    """Порядок «по риску»: высокий риск первым, внутри — сервисы из утечек, затем по баллу."""
    r = s["risk"]
    return (LEVEL_ORDER[r["level"]], not r["breached"], -r["score"], -(s.get("count") or 0), s["domain"])


def is_closed(s: dict) -> bool:
    """Риск снят: аккаунт удалён, оставлен/пропущен осознанно или отписка выполнена."""
    decision = s.get("decision")
    if decision in ("keep", "skip"):
        return True
    if decision == "delete":
        return s.get("status") == "deleted"
    if decision == "unsubscribe":
        return bool(s.get("unsub_done"))
    return False
