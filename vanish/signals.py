"""Сигналы наличия аккаунта в темах писем и фильтр шума."""

from __future__ import annotations

import json
import re
from functools import lru_cache

from . import RESOURCES_DIR
from .psl import root_domain

# Уровни уверенности (по убыванию).
SURE = "sure"          # точно аккаунт
LIKELY = "likely"      # вероятно
NEWSLETTER = "newsletter"  # только рассылка
PERSONAL = "personal"  # переписка с людьми — шум

CONFIDENCE_ORDER = {SURE: 0, LIKELY: 1, NEWSLETTER: 2, PERSONAL: 3}

# Сильные сигналы: такие письма приходят почти только владельцам аккаунта.
STRONG_PATTERNS = [
    # RU
    r"добро пожаловать",
    r"подтверд\w* (?:ваш\w* |свой |свою )?(?:e-?mail|почт|адрес|электронн|регистрац|аккаунт|учётн|учетн)",
    r"подтверждени\w* (?:e-?mail|почты|адреса|регистрации|аккаунта)",
    r"регистрац",
    r"зарегистрир",
    r"(?:ваш|вашего|вашем|вашу|вашей) (?:аккаунт|учётн|учетн|профил|личн\w* кабинет)",
    r"(?:сброс|восстановлени|смен|изменени)\w* пароля",
    r"(?:новый|ваш|временный) пароль",
    r"код (?:для )?(?:входа|подтверждения|доступа|авторизации|верификации)",
    r"одноразов\w* код",
    r"вход (?:в|на) (?:ваш|аккаунт|учётн|учетн|личн)",
    r"новый вход",
    r"активац\w* (?:аккаунт|учётн|учетн|профил)",
    r"(?:аккаунт|учётная запись|учетная запись) (?:создан|активирован|удал|заблокир)",
    # EN
    r"\bwelcome\b",
    r"\bverify (?:your |my )?(?:e-?mail|account|address|identity)",
    r"\bconfirm (?:your |my )?(?:e-?mail|account|address|registration|sign ?up)",
    r"\bverification code\b",
    r"\bemail (?:address )?(?:verification|confirmation)\b",
    r"\bactivate (?:your )?account\b",
    r"\baccount (?:created|activated|confirmation|verification|deleted|locked|suspended)\b",
    r"\byour (?:new )?account\b",
    r"\byour [\w.-]+ account\b",
    r"\b(?:access|log ?in|sign-?in) (?:to|from) (?:your|a new)\b",
    r"\bsign(?:ed)? ?up\b",
    r"\bregistration\b",
    r"\bpassword (?:reset|change|changed|recovery)\b",
    r"\breset (?:your )?password\b",
    r"\b(?:login|log-in|log in|sign-in|sign in|security|one-time|access|2fa) code\b",
    r"\bnew (?:login|sign-in|sign in|device)\b",
    r"\b(?:magic|login|sign-in) link\b",
    r"\bthanks? (?:you )?for (?:signing up|registering|joining|creating)\b",
]

# Слабые сигналы: указывают на отношения с сервисом (покупки, подписки, безопасность).
WEAK_PATTERNS = [
    # RU
    r"аккаунт",
    r"учётн\w* запис|учетн\w* запис",
    r"профил",
    r"личн\w* кабинет",
    r"пароль",
    r"заказ",
    r"чек\b|электронный чек|квитанц",
    r"оплат|платёж|платеж|счёт на оплату|счет на оплату",
    r"подписк",
    r"доставк",
    r"бронировани",
    r"бонус\w* (?:счёт|счет|баланс)|баллы",
    r"безопасност",
    r"двухфакторн|двухэтапн",
    r"уведомлени\w* о входе",
    # EN
    r"\baccount\b",
    r"\bprofile\b",
    r"\bpassword\b",
    r"\border\b",
    r"\breceipt\b",
    r"\binvoice\b",
    r"\bpayment\b",
    r"\bsubscription\b",
    r"\bbilling\b",
    r"\bshipped\b|\bdelivery\b",
    r"\bbooking\b|\breservation\b",
    r"\bpurchase\b",
    r"\bsecurity alert\b",
    r"\btwo-factor\b|\b2-step\b",
    r"\btrial\b",
    r"\bmembership\b",
]

_STRONG = re.compile("|".join(f"(?:{p})" for p in STRONG_PATTERNS), re.IGNORECASE)
_WEAK = re.compile("|".join(f"(?:{p})" for p in WEAK_PATTERNS), re.IGNORECASE)

# Служебные локальные части адреса: у почтовых провайдеров они означают сервис, а не человека.
SYSTEM_LOCAL_RE = re.compile(
    r"^(?:no-?reply|do-?not-?reply|donotreply|noreply-\w+|robot|info|support|help|notify|notifications?|"
    r"alerts?|security|account|accounts|mailer|mailer-daemon|postmaster|news|newsletter|hello|team|admin|"
    r"service|billing|password|passport|id|auth|verify|confirm|welcome|marketing|promo)\b",
    re.IGNORECASE,
)


def subject_signal(subject: str) -> int:
    """2 — сильный сигнал, 1 — слабый, 0 — нет сигнала."""
    if not subject:
        return 0
    if _STRONG.search(subject):
        return 2
    if _WEAK.search(subject):
        return 1
    return 0


def classify(strong_hits: int, weak_hits: int, sent_to: int) -> str:
    if strong_hits > 0:
        return SURE
    if weak_hits > 0:
        return LIKELY
    if sent_to > 0:
        return PERSONAL
    return NEWSLETTER


@lru_cache(maxsize=1)
def mail_providers() -> frozenset[str]:
    path = RESOURCES_DIR / "mail_providers.txt"
    items = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.split("#", 1)[0].strip().lower()
        if line:
            items.add(line)
    return frozenset(items)


@lru_cache(maxsize=1)
def domain_aliases() -> dict[str, str]:
    path = RESOURCES_DIR / "domain_aliases.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    return {k.lower(): v.lower() for k, v in data.items() if not k.startswith("_")}


def is_personal_sender(address: str, host: str) -> bool:
    """Письмо от человека с публичного почтового сервиса (gmail.com, mail.ru, ...)."""
    if host not in mail_providers():
        return False
    local = address.partition("@")[0]
    return not SYSTEM_LOCAL_RE.match(local)


def service_domain(host: str) -> str | None:
    """Корневой домен сервиса или None, если домен технический (ESP)."""
    root = root_domain(host)
    if not root or "." not in root:
        return None
    aliases = domain_aliases()
    if root in aliases:
        return aliases[root] or None
    return root
