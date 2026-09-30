from pathlib import Path

import pytest

from vanish.analyzer import analyze
from vanish.store import connect
from vanish.synthetic import write_mbox


@pytest.fixture(scope="session")
def mbox_path(tmp_path_factory) -> Path:
    path = tmp_path_factory.mktemp("mbox") / "synthetic.mbox"
    write_mbox(path)
    return path


@pytest.fixture(scope="session")
def mbox_crlf_path(tmp_path_factory) -> Path:
    path = tmp_path_factory.mktemp("mbox") / "synthetic_crlf.mbox"
    write_mbox(path, crlf=True)
    return path


@pytest.fixture
def conn(tmp_path):
    c = connect(tmp_path / "test.db")
    yield c
    c.close()


@pytest.fixture
def analyzed(conn, mbox_path):
    analyze(conn, mbox_path)
    return conn
