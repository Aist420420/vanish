import pytest

from vanish.signals import (
    LIKELY, NEWSLETTER, PERSONAL, SURE, classify, is_personal_sender, subject_signal,
)


@pytest.mark.parametrize(
    "subject",
    [
        "Добро пожаловать в Ozon!",
        "Подтвердите ваш email",
        "Подтвердите регистрацию на Хабре",
        "Сброс пароля",
        "Код для входа: 4815",
        "Код подтверждения: 123456",
        "Новый вход в аккаунт",
        "Ваш аккаунт заблокирован",
        "Welcome to Netflix, Alex!",
        "[GitHub] Please verify your email address",
        "Confirm your email address",
        "Password reset request",
        "Reset your password",
        "Your login code is 1234",
        "Your sign-in link for Medium",
        "Your Steam account: Access from new web or mobile device",
        "Notion was granted access to your Google Account",
        "Thanks for signing up!",
    ],
)
def test_strong_signals(subject):
    assert subject_signal(subject) == 2


@pytest.mark.parametrize(
    "subject",
    [
        "Ваш заказ готов к выдаче",
        "Статус заказа изменён",
        "Ваше бронирование подтверждено",
        "Your Spotify Premium receipt",
        "Update your payment information",
        "Security alert",
        "Thank you for your Steam purchase!",
    ],
)
def test_weak_signals(subject):
    assert subject_signal(subject) == 1


@pytest.mark.parametrize(
    "subject",
    ["Скидки недели: до −70% на технику", "Medium Daily Digest", "Top 10 in your country", "", "Главное за неделю"],
)
def test_no_signal(subject):
    assert subject_signal(subject) == 0


def test_classify_levels():
    assert classify(1, 0, 0) == SURE
    assert classify(0, 3, 5) == LIKELY
    assert classify(0, 0, 0) == NEWSLETTER
    assert classify(0, 0, 2) == PERSONAL


@pytest.mark.parametrize(
    "address, host, personal",
    [
        ("ivan.petrov@gmail.com", "gmail.com", True),
        ("anna@mail.ru", "mail.ru", True),
        ("noreply@mail.ru", "mail.ru", False),        # служебный адрес провайдера — это сервис
        ("robot@yandex.ru", "yandex.ru", False),
        ("noreply@id.yandex.ru", "id.yandex.ru", False),  # поддомен провайдера — сервис
        ("noreply@github.com", "github.com", False),
    ],
)
def test_personal_sender(address, host, personal):
    assert is_personal_sender(address, host) is personal
