import http.client
import io
import json
import threading
import zipfile

from instrumentzero.server import make_server


def test_installed_edge_api_preserves_result_export_and_rejects_bad_signal():
    server = make_server(0)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    port = server.server_port

    def request(path, payload=None):
        connection = http.client.HTTPConnection('127.0.0.1', port, timeout=120)
        headers = {'Content-Type': 'application/json', 'Origin': f'http://127.0.0.1:{port}'}
        connection.request('GET' if payload is None else 'POST', path,
                           body=json.dumps(payload) if payload is not None else None, headers=headers)
        response = connection.getresponse()
        code, data = response.status, response.read()
        connection.close()
        return code, data

    try:
        assert request('/edge')[0] == 200
        assert request('/edge.js')[0] == 200
        code, data = request('/api/edge/run', {'scenario': 'mount_b', 'seconds': 4})
        assert code == 200, data
        result = json.loads(data)
        assert result['comparisons'][0]['result']['frequency_hz'] > 22
        code, exported = request(result['artifact_url'])
        assert code == 200
        with zipfile.ZipFile(io.BytesIO(exported)) as archive:
            assert json.loads(archive.read('run.json'))['compiled'] == result['compiled']
            assert 'raw.izp' in archive.namelist()
        code, data = request('/api/edge/run', {'scenario': 'saturation'})
        assert code == 422 and 'clip' in json.loads(data)['error']
        code, data = request('/api/edge/run', {'scenario': 'silence'})
        assert code == 200
        assert json.loads(data)['comparisons'][0]['result']['status'] == 'rejected'
    finally:
        server.shutdown()
        server.server_close()
        worker.join()
