import pytest

from vanish.psl import root_domain


@pytest.mark.parametrize(
    "host, expected",
    [
        ("mail.ozon.ru", "ozon.ru"),
        ("ozon.ru", "ozon.ru"),
        ("email.bbc.co.uk", "bbc.co.uk"),
        ("noreply.rozetka.com.ua", "rozetka.com.ua"),
        ("a.b.c.github.com", "github.com"),
        ("MAIL.Notion.SO.", "notion.so"),
        ("shop.example.com.au", "example.com.au"),
        ("id.yandex.ru", "yandex.ru"),
        ("sub.example.unknowntld", "example.unknowntld"),
        ("почта.рф", "xn--80a1acny.xn--p1ai"),
        ("mail.почта.рф", "xn--80a1acny.xn--p1ai"),
    ],
)
def test_root_domain(host, expected):
    assert root_domain(host) == expected


def test_wildcard_and_exception_rules():
    # *.ck — любая метка под ck является суффиксом, но !www.ck — исключение.
    assert root_domain("shop.foo.ck") == "shop.foo.ck"
    assert root_domain("a.www.ck") == "www.ck"


def test_bad_input():
    assert root_domain("") == ""
    assert root_domain("   ") == ""
