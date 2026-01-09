from fastapi.testclient import TestClient

import server.main as main
from server.agents import sessions as sessions_module
from server.auth import create_access_token


def _client():
    return TestClient(main.app)


def test_upload_endpoint_roundtrip(tmp_path):
    client = _client()
    # create a session folder programmatically
    sid, meta = sessions_module.create_session_folder('Upload Test Session', 'test@example.com')
    # token for seeded dev user
    token = create_access_token('test@example.com')
    headers = {'Authorization': f'Bearer {token}'}
    # upload a simple text file
    data = {'name': 'upload.txt'}
    files = {'file': ('upload.txt', b'Hello Binary Upload', 'text/plain')}
    resp = client.post(f"/documents/{sid}/upload", headers=headers, files=files, data=data)
    assert resp.status_code == 201, resp.text
    saved = resp.json()
    assert saved.get('session_id') == sid
    assert saved.get('name') == 'upload.txt'
    assert saved.get('filename')
    # list documents
    resp = client.get(f"/documents/{sid}", headers=headers)
    assert resp.status_code == 200, resp.text
    docs = resp.json()
    assert any(d['id'] == saved['id'] for d in docs)
    # fetch detail
    resp = client.get(f"/documents/{sid}/{saved['id']}", headers=headers)
    assert resp.status_code == 200, resp.text
    detail = resp.json()
    assert detail.get('filename')
    # content might be raw text for text uploads
    assert 'Hello' in detail.get('content', '')
