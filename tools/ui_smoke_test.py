import requests

API = 'http://127.0.0.1:8000'

def run():
    s = requests.Session()
    resp = s.post(f'{API}/player/login', json={'email':'test@example.com','password':'secret'})
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
