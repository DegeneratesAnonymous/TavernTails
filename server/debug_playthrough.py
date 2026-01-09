import time

from fastapi.testclient import TestClient

import server.main as m

c = TestClient(m.app)
email = f"tc{time.time()}@example.com"
print('EMAIL', email)
# signup
r = c.post('/player/signup', json={'email': email, 'password': 'secret', 'name': 'TC'})
print('SIGNUP', r.status_code, r.json())
# verify
token = r.json().get('verification_token')
r2 = c.post('/player/verify-email', json={'email': email, 'token': token})
print('VERIFY', r2.status_code, r2.json())
# login
r3 = c.post('/player/login', json={'email': email, 'password': 'secret'})
print('LOGIN', r3.status_code, r3.json())
print('LOGIN KEYS:', list(r3.json().keys()))
print('ACCESS_TOKEN repr:', repr(r3.json().get('access_token')))
# attempt create session
token = r3.json().get('access_token')
headers = {'Authorization': f'Bearer {token}'}
r4 = c.post('/sessions', json={'name':'session1'}, headers=headers)
print('CREATE SESSION', r4.status_code, r4.text)
# attempt invite (if session created)
if r4.status_code == 201:
    sid = r4.json().get('id')
    r5 = c.post(f'/sessions/{sid}/invite', json={'email': 'friend@example.com'}, headers=headers)
    print('INVITE', r5.status_code, r5.text)
else:
    print('No session created; skipping invite')
