"""Генератор синтетического mbox (фейковые письма) для тестов и демо-режима."""

from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone
from email.charset import QP, Charset
from email.header import Header
from email.utils import format_datetime
from pathlib import Path

ME = "me.vanish.demo@gmail.com"

# (адрес отправителя, имя, [(тема, год, есть List-Unsubscribe)])
SERVICES: list[tuple[str, str, list[tuple[str, int, bool]]]] = [
    ("noreply@mail.ozon.ru", "OZON", [
        ("Добро пожаловать в Ozon!", 2017, False),
        ("Ваш заказ №48213 оформлен", 2019, False),
        ("Скидки недели: до −70% на технику", 2022, True),
        ("Распродажа выходного дня", 2023, True),
        ("Вам начислены баллы", 2024, True),
    ]),
    ("noreply@github.com", "GitHub", [
        ("[GitHub] Please verify your email address", 2015, False),
        ("[GitHub] A new SSH key was added to your account", 2018, False),
        ("[GitHub] Your personal access token has expired", 2023, False),
    ]),
    ("info@mailer.netflix.com", "Netflix", [
        ("Welcome to Netflix, Alex!", 2016, False),
        ("Update your payment information", 2020, False),
        ("New arrivals this week", 2021, True),
        ("Top 10 in your country", 2022, True),
    ]),
    ("no-reply@spotify.com", "Spotify", [
        ("Confirm your email address", 2017, False),
        ("Your Spotify Premium receipt", 2019, False),
        ("Your 2023 Wrapped is here", 2023, True),
    ]),
    ("noreply@steampowered.com", "Steam", [
        ("Your Steam account: Access from new web or mobile device", 2014, False),
        ("Thank you for your Steam purchase!", 2016, False),
        ("An item on your Steam wishlist is on sale!", 2020, True),
    ]),
    ("security@facebookmail.com", "Facebook", [
        ("Password reset request", 2012, False),
        ("You have 3 new notifications", 2013, True),
        ("Someone tried to log into your account", 2019, False),
    ]),
    ("noreply@habr.com", "Хабр", [
        ("Подтвердите регистрацию на Хабре", 2016, False),
        ("Лучшие статьи недели", 2021, True),
        ("Лучшие статьи недели", 2022, True),
    ]),
    ("info@wildberries.ru", "Wildberries", [
        ("Код для входа: 4815", 2020, False),
        ("Ваш заказ доставлен в пункт выдачи", 2021, False),
        ("Горячие скидки только сегодня", 2023, True),
    ]),
    ("order@dns-shop.ru", "DNS", [
        ("Ваш заказ готов к выдаче", 2019, False),
        ("Статус заказа изменён", 2019, False),
    ]),
    ("noreply@avito.ru", "Авито", [
        ("Новый вход в аккаунт", 2018, False),
        ("Ваше объявление опубликовано", 2018, False),
        ("Похожие объявления для вас", 2020, True),
    ]),
    ("news@skyeng.ru", "Skyeng", [
        ("Как выучить английский за 3 месяца", 2020, True),
        ("5 ошибок в английском, которые делают все", 2021, True),
        ("Бесплатный вебинар в четверг", 2021, True),
    ]),
    ("noreply@medium.com", "Medium", [
        ("Your sign-in link for Medium", 2019, False),
        ("Medium Daily Digest", 2020, True),
        ("Medium Daily Digest", 2021, True),
    ]),
    ("no-reply@coursera.org", "Coursera", [
        ("Welcome to Coursera!", 2015, False),
        ("Your course starts tomorrow", 2015, True),
    ]),
    ("hello@duolingo.com", "Duolingo", [
        ("Time for your daily lesson", 2022, True),
        ("You're on fire! Keep it going", 2022, True),
    ]),
    ("noreply@booking.com", "Booking.com", [
        ("Ваше бронирование подтверждено", 2019, False),
        ("Специальные предложения для вас", 2020, True),
    ]),
    ("transaction@notice.aliexpress.ru", "AliExpress", [
        ("Заказ отправлен", 2018, False),
        ("Заказ получен — оцените товар", 2018, False),
    ]),
    ("noreply@id.yandex.ru", "Яндекс ID", [
        ("Код подтверждения: 123456", 2021, False),
        ("Изменение пароля", 2022, False),
    ]),
    ("digest@vc.ru", "vc.ru", [
        ("Главное за неделю", 2021, True),
        ("Главное за неделю", 2022, True),
    ]),
    ("newsletter@email.bbc.co.uk", "BBC", [
        ("Your weekly BBC newsletter", 2020, True),
        ("Welcome to BBC Account", 2020, False),
    ]),
    ("noreply@rozetka.com.ua", "ROZETKA", [
        ("Добро пожаловать в ROZETKA", 2017, False),
        ("Акции недели", 2018, True),
    ]),
    ("team@mail.notion.so", "Notion", [
        ("Welcome to Notion", 2021, False),
        ("What's new in Notion", 2022, True),
    ]),
    ("no-reply@accounts.google.com", "Google", [
        ("Security alert", 2020, False),
        ("Notion was granted access to your Google Account", 2021, False),
        ("Figma was granted access to your Google Account", 2022, False),
    ]),
    ("no-reply@figma.com", "Figma", [
        ("Verify your email", 2022, False),
    ]),
    ("hi@producthunt.com", "Product Hunt", [
        ("Today's top products", 2019, True),
    ]),
    ("bounce-123@sendgrid.net", "", [
        ("Your invoice", 2020, False),
    ]),
    ("noreply@2gis.ru", "2ГИС", [
        ("Ваш отзыв опубликован", 2018, False),
    ]),
    ("news@some-very-old-forum.net", "Old Forum", [
        ("Регистрация на форуме завершена", 2009, False),
        ("Новые сообщения в теме", 2010, False),
    ]),
]

PERSONAL = [
    ("ivan.petrov@gmail.com", "Иван Петров", "Привет! Фото с выходных", 2021),
    ("anna.smirnova@mail.ru", "Анна", "Re: встреча в субботу", 2022),
    ("olga@yandex.ru", "Ольга", "Поздравляю с днём рождения!", 2023),
]

COLLEAGUE = ("sergey@acme-corp.com", "Сергей (ACME)", "Отчёт за квартал", 2022)
SPAM = ("winner@casino-bonus.xyz", "Casino", "Вы выиграли 1 000 000!", 2023)


# Рассылки, у которых в List-Unsubscribe только mailto: (https-ссылки нет).
MAILTO_ONLY = {"hi@producthunt.com", "digest@vc.ru"}
# Письмо сервиса с аккаунтом, попавшее в «Спам».
SERVICE_IN_SPAM = ("noreply@habr.com", "Хабр", "Вам подарок! Заберите до конца дня", 2023)


def _encode_subject(subject: str, style: int) -> str:
    if subject.isascii():
        return subject
    if style == 0:
        return subject  # «сырой» UTF-8 — встречается в реальных архивах
    if style == 1:
        return Header(subject, "utf-8").encode()  # base64
    qp = Charset("utf-8")
    qp.header_encoding = QP
    return Header(subject, qp).encode(maxlinelen=40)  # quoted-printable, со свёрткой строк


def _encode_name(name: str) -> str:
    return Header(name, "utf-8").encode() if name and not name.isascii() else name


def _message(rng: random.Random, n: int, sender: str, name: str, subject: str, dt: datetime,
             unsub: bool, labels: str, to: str = ME, message_id: bool = True) -> str:
    sep_date = dt.strftime("%a %b %d %H:%M:%S +0000 %Y")
    from_hdr = f"{_encode_name(name)} <{sender}>" if name else sender
    lines = [
        f"From {1700000000000000000 + n}@xxx {sep_date}",
        f"X-GM-THRID: {1600000000000000000 + n}",
        f"X-Gmail-Labels: {labels}",
        f"Delivered-To: {ME}",
        "Received: by 2002:a05:6a10:1234 with SMTP id x1csp1234;",
        f"        {format_datetime(dt)}",
        f"From: {from_hdr}",
        f"To: {to}",
        f"Subject: {_encode_subject(subject, n % 3)}",
        f"Date: {format_datetime(dt)}",
    ]
    if message_id:
        lines.append(f"Message-ID: <synthetic-{n}@{sender.split('@')[1]}>")
    if unsub:
        host = sender.split("@")[1]
        if sender in MAILTO_ONLY:
            lines.append(f"List-Unsubscribe: <mailto:unsub-{n}@{host}>")
        else:
            # Длинный заголовок свёрнут на две строки, как в настоящих письмах.
            lines.append(f"List-Unsubscribe: <mailto:unsub-{n}@{host}>,")
            # Зона .invalid никогда не резолвится: клик в демо не уйдёт на настоящий сайт.
            lines.append(f" <https://{host}.invalid/unsubscribe?u=synthetic-{n}>")
    lines += [
        "MIME-Version: 1.0",
        'Content-Type: text/plain; charset="UTF-8"',
        "",
        "Это синтетическое тестовое письмо.",
        "",
        "From here on this line looks like a separator but is not one.",
        ">From an escaped mboxrd line.",
        "SECRET-BODY-MARKER: тело письма не должно никуда попадать.",
        "",
    ]
    return "\n".join(lines)


def build_messages(seed: int = 42) -> list[str]:
    rng = random.Random(seed)
    messages: list[str] = []
    n = 0

    def when(year: int) -> datetime:
        return datetime(year, rng.randint(1, 12), rng.randint(1, 28), rng.randint(0, 23),
                        rng.randint(0, 59), tzinfo=timezone.utc)

    for sender, name, subjects in SERVICES:
        for subject, year, unsub in subjects:
            n += 1
            messages.append(_message(rng, n, sender, name, subject, when(year), unsub, "Входящие,Непрочитанные"))

    # Повторы рассылок — «шумные» сервисы.
    for sender, name, subject, count in [
        ("news@skyeng.ru", "Skyeng", "Новая подборка уроков", 12),
        ("info@mailer.netflix.com", "Netflix", "Tonight's recommendations", 8),
        ("noreply@mail.ozon.ru", "OZON", "Персональные скидки", 6),
    ]:
        for i in range(count):
            n += 1
            messages.append(_message(rng, n, sender, name, subject, when(2020 + i % 5), True, "Входящие,Промоакции"))

    for sender, name, subject, year in PERSONAL:
        n += 1
        messages.append(_message(rng, n, sender, name, subject, when(year), False, "Входящие"))

    n += 1
    messages.append(_message(rng, n, COLLEAGUE[0], COLLEAGUE[1], COLLEAGUE[2], when(COLLEAGUE[3]), False, "Входящие"))
    n += 1
    sender, name, subject, year = SERVICE_IN_SPAM
    messages.append(_message(rng, n, sender, name, subject, when(year), True, "Спам"))
    n += 1
    messages.append(_message(rng, n, ME, "Я", "Re: Отчёт за квартал", when(2022), False, "Отправленные",
                             to=COLLEAGUE[0]))
    n += 1
    messages.append(_message(rng, n, SPAM[0], SPAM[1], SPAM[2], when(SPAM[3]), False, "Спам"))
    # Письмо без Message-ID и письмо, которое я отправил сам себе.
    n += 1
    messages.append(_message(rng, n, "noreply@2gis.ru", "2ГИС", "Добро пожаловать в 2ГИС", when(2017), False,
                             "Входящие", message_id=False))
    n += 1
    messages.append(_message(rng, n, ME, "Я", "Заметка себе", when(2023), False, "Входящие,Отправленные", to=ME))
    return messages


def write_mbox(path: Path, seed: int = 42, crlf: bool = False) -> int:
    messages = build_messages(seed)
    text = "\n".join(messages)
    if crlf:
        text = text.replace("\n", "\r\n")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(text.encode("utf-8"))
    return len(messages)
