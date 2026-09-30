import pytest

from vanish import __main__ as cli


@pytest.fixture
def calls(monkeypatch):
    seen = []
    for name in ("cmd_start", "cmd_serve", "cmd_analyze", "cmd_demo"):
        monkeypatch.setattr(cli, name, lambda args, name=name: seen.append((name, args)) or 0)
    return seen


@pytest.mark.parametrize(
    "argv, command",
    [
        ([], "cmd_start"),
        (["--no-browser", "--port", "9000"], "cmd_start"),
        (["--db", "x.db", "--no-browser"], "cmd_start"),
        (["--db=x.db"], "cmd_start"),
        (["serve", "--port", "9000"], "cmd_serve"),
        (["--db", "x.db", "analyze", "a.mbox"], "cmd_analyze"),
        (["demo", "--reset"], "cmd_demo"),
    ],
)
def test_default_command_is_start(calls, argv, command):
    assert cli.main(argv) == 0
    assert calls[0][0] == command


def test_start_keeps_options(calls):
    cli.main(["--db", "x.db", "--no-browser", "--port", "9000"])
    args = calls[0][1]
    assert (args.db, args.no_browser, args.port) == ("x.db", True, 9000)
