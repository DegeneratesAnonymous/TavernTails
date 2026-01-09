import os

import boto3
import pytest
from fastapi.testclient import TestClient

import server.main as main
from server.agents import sessions as sessions_module
from server.auth import create_access_token
from server.storage.documents import S3DocumentStore

try:
    from moto import mock_aws  # type: ignore
except Exception:  # pragma: no cover - moto missing
    pytest.skip("moto.mock_aws not available", allow_module_level=True)


@pytest.fixture(autouse=True)
def reset_storage_env():
    # ensure each test configures storage fresh to avoid env leakage
    yield
    for key in ("TAVERNTAILS_STORAGE_MODE", "TAVERNTAILS_S3_BUCKET", "TAVERNTAILS_S3_PREFIX"):
        os.environ.pop(key, None)
    import server.storage.documents as docs
    import server.agents.documents as doc_router

    docs._store = None
    # reset router store back to default local store for subsequent tests
    doc_router.store = docs.get_document_store()


@mock_aws
def test_presign_and_register_roundtrip():
    # create fake S3
    s3 = boto3.client('s3', region_name='us-east-1')
    bucket = 'test-bucket'
    s3.create_bucket(Bucket=bucket)
    # swap store to S3DocumentStore
    os.environ['TAVERNTAILS_STORAGE_MODE'] = 's3'
    os.environ['TAVERNTAILS_S3_BUCKET'] = bucket
    # re-import store factory and reset cached store so env vars take effect
    import importlib
    import server.storage.documents as docs
    docs._store = None
    store = docs.get_document_store()
    assert isinstance(store, S3DocumentStore)
    # ensure documents router picks up the mocked store instance
    import server.agents.documents as doc_router

    doc_router.store = store

    client = TestClient(main.app)
    sid, meta = sessions_module.create_session_folder('S3 Session', 'test@example.com')
    token = create_access_token('test@example.com')
    headers = {'Authorization': f'Bearer {token}'}

    # request presign
    resp = client.post(f"/documents/{sid}/presign", json={'filename': 'upload.png', 'content_type': 'image/png'}, headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert 'url' in body and 'fields' in body

    # simulate direct upload via boto3 using fields/key
    key = body['fields'].get('key') or f"{sid}/docs/upload.png"
    s3.put_object(Bucket=bucket, Key=key, Body=b'PNGDATA')

    # register the uploaded object
    register = client.post(f"/documents/{sid}/register", json={'filename': key, 'name': 'upload.png', 'size': 7}, headers=headers)
    assert register.status_code == 200
    saved = register.json()
    assert saved['name'] == 'upload.png'
    assert saved['filename'].endswith('.png')

    detail = client.get(f"/documents/{sid}/{saved['id']}", headers=headers)
    assert detail.status_code == 200
    payload = detail.json()
    assert payload['filename'].endswith('.png')
    assert payload['content']
