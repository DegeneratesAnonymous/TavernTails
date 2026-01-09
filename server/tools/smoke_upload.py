import requests

from server.agents import sessions as sessions_module
from server.auth import create_access_token

sid, meta = sessions_module.create_session_folder('Smoke Session', 'test@example.com')
print('Created session', sid)

token = create_access_token('test@example.com')
print('Using token (truncated):', token[:20])

url = f'http://127.0.0.1:8000/documents/{sid}/upload'
headers = {'Authorization': f'Bearer {token}'}
files = {'file': ('smoke.txt', b'Hello smoke upload', 'text/plain')}
resp = requests.post(url, headers=headers, files=files, data={'name': 'smoke.txt'})
print('Response:', resp.status_code)
try:
    print(resp.json())
except Exception:
    print(resp.text)
