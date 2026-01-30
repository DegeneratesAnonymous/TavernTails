import requests

API = 'http://127.0.0.1:8000'


def ensure_test_user(session: requests.Session, *, email: str, password: str) -> None:
    """Ensure the test user exists and is verified.

    - If the user already exists, do nothing.
    - If the user is created, auto-verify using the returned dev verification token.
    """
    signup = session.post(f'{API}/player/signup', json={'email': email, 'password': password, 'name': 'Test User'})
    if signup.status_code == 409:
        return
    if signup.status_code != 200:
        raise RuntimeError(f'Signup failed: {signup.status_code} {signup.text}')
    token = (signup.json() or {}).get('verification_token')
    if not token:
        raise RuntimeError('Signup succeeded but verification_token missing')
    verify = session.post(f'{API}/player/verify-email', json={'email': email, 'token': token})
    if verify.status_code != 200:
        raise RuntimeError(f'Verify failed: {verify.status_code} {verify.text}')

def run():
    s = requests.Session()
    email = 'test@example.com'
    password = 'secret'
    ensure_test_user(s, email=email, password=password)

    resp = s.post(f'{API}/player/login', json={'email': email, 'password': password})
    if resp.status_code != 200:
        print('Login failed', resp.status_code, resp.text)
        return 2
    data = resp.json()
    token = data.get('access_token')
    headers = {'Authorization': f'Bearer {token}'}
    me = s.get(f'{API}/player/me', headers=headers)
    if me.status_code == 200:
        print('GET /player/me OK:', me.json())
        return 0
    else:
        print('GET /player/me failed', me.status_code, me.text)
        return 3

if __name__ == '__main__':
    raise SystemExit(run())
