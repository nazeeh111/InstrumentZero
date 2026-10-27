import http.client
import json
import threading
from pathlib import Path

import pytest

from instrumentzero.examples import stiffness_example
from instrumentzero.server import make_server


@pytest.fixture
def lab_server():
    server = make_server(0, Path(__file__).parents[1] / "data")
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    yield server.server_port
    server.shutdown()
    server.server_close()
    worker.join()


def request(port, path, body=None, headers=None):
    connection = http.client.HTTPConnection("127.0.0.1", port)
    connection.request("GET" if body is None else "POST", path,
                       body=None if body is None else json.dumps(body), headers=headers or {})
    response = connection.getresponse()
    status, data, mime = response.status, response.read(), response.getheader("Content-Type")
    connection.close()
    return status, data, mime


def test_local_api_and_actual_export(lab_server):
    code, body, _ = request(lab_server, "/api/health")
    assert code == 200
    assert json.loads(body)["device_connections"] == 0
    code, body, _ = request(lab_server, "/api/session")
    token = json.loads(body)["token"]
    bundle = stiffness_example()
    payload = {"spec": bundle["spec"], "rows": bundle["rows"]}
    headers = {"Content-Type": "application/json", "X-InstrumentZero-Token": token}
    code, body, _ = request(lab_server, "/api/analyze", payload, headers)
    assert code == 200
    assert json.loads(body)["quantity"]["value"] == bundle["result"]["quantity"]["value"]
    code, body, mime = request(lab_server, "/api/export", payload, headers)
    assert code == 200 and mime == "application/zip" and body.startswith(b"PK")


def test_reject_cross_origin_and_dns_rebinding(lab_server):
    payload = {"spec": stiffness_example()["spec"], "rows": []}
    code, _, _ = request(lab_server, "/api/analyze", payload,
                         {"Content-Type": "application/json", "Origin": "https://untrusted.example"})
    assert code == 403
    code, _, _ = request(lab_server, "/api/health", headers={"Host": "untrusted.example"})
    assert code == 403
    code, _, _ = request(lab_server, "/api/analyze", payload, {"Content-Type": "application/json"})
    assert code == 403


def test_invalid_json_shapes_are_explained(lab_server):
    headers = {"Content-Type": "application/json", "Origin": f"http://127.0.0.1:{lab_server}"}
    code, body, _ = request(lab_server, "/api/compile", [], headers)
    assert code == 422
    assert "object" in json.loads(body)["error"]
    code, _, _ = request(lab_server, "/../../pyproject.toml")
    assert code == 404
