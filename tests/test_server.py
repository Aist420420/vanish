import http.client
import json
import threading

import pytest

from vanish.analyzer import analyze
from vanish.server import HOST, App, LocalServer, make_handler


@pytest.fixture
def server(tmp_path, mbox_path):
    static = tmp_path / "static"
    static.mkdir()
    (static / "index.html").write_text("<!doctype html><title>Vanish</title>", encoding="utf-8")
    app = App(tmp_path / "srv.db", static_dir=static)
    analyze(app.conn, mbox_path)
    holder = {"port": 0}
    httpd = LocalServer((HOST, 0), make_handler(app, holder))
    holder["port"] = httpd.server_address[1]
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield holder["port"]
    httpd.shutdown()
    httpd.server_close()
    app.conn.close()


def request(port, method, path, body=None, headers=None):
    conn = http.client.HTTPConnection(HOST, port, timeout=5)
    hdrs = {"Host": f"127.0.0.1:{port}"}
    if body is not None:
        hdrs["Content-Type"] = "application/json"
    hdrs.update(headers or {})
    conn.request(method, path, body=json.dumps(body) if body is not None else None, headers=hdrs)
    resp = conn.getresponse()
    data = resp.read()
    conn.close()
    return resp.status, resp.getheader("Content-Type") or "", data


def test_state_and_decide(server):
    status, ctype, data = request(server, "GET", "/api/state")
    assert status == 200 and ctype.startswith("application/json")
    state = json.loads(data)
    assert any(s["domain"] == "ozon.ru" for s in state["services"])

    status, _, data = request(server, "POST", "/api/decide", {"domain": "ozon.ru", "decision": "keep"})
    assert status == 200
    assert json.loads(data)["service"]["decision"] == "keep"

    status, _, data = request(server, "POST", "/api/undo", {})
    assert status == 200 and json.loads(data)["service"]["decision"] is None


def test_errors(server):
    status, _, data = request(server, "POST", "/api/decide", {"domain": "ozon.ru", "decision": "boom"})
    assert status == 400 and "error" in json.loads(data)
    status, _, _ = request(server, "GET", "/api/nothing")
    assert status == 404


def test_rejects_foreign_host_and_origin(server):
    status, _, _ = request(server, "GET", "/api/state", headers={"Host": "evil.example:80"})
    assert status == 403
    status, _, _ = request(server, "POST", "/api/decide", {"domain": "ozon.ru", "decision": "keep"},
                           headers={"Origin": "http://evil.example"})
    assert status == 403


def test_rejects_non_json_post(server):
    conn = http.client.HTTPConnection(HOST, server, timeout=5)
    conn.request("POST", "/api/decide", body="domain=ozon.ru&decision=keep",
                 headers={"Host": f"127.0.0.1:{server}", "Content-Type": "application/x-www-form-urlencoded"})
    assert conn.getresponse().status == 415
    conn.close()


def test_static_and_downloads(server):
    status, ctype, data = request(server, "GET", "/")
    assert status == 200 and b"Vanish" in data
    status, _, data = request(server, "GET", "/some/spa/route")
    assert status == 200 and b"Vanish" in data
    status, _, data = request(server, "GET", "/../../etc/passwd")
    assert status == 200 and b"Vanish" in data
    status, ctype, data = request(server, "GET", "/api/export.csv")
    assert status == 200 and ctype.startswith("text/csv") and "Домен".encode() in data
    status, _, data = request(server, "GET", "/api/progress.json")
    assert status == 200 and json.loads(data)["app"] == "vanish"


def test_listens_only_on_localhost():
    assert HOST == "127.0.0.1"
