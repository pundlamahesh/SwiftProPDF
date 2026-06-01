import requests

BASE='http://127.0.0.1:5000'
EMAIL='pundlamahesh@gmail.com'
PASSWORD='AdminPass123!'

s = requests.Session()

print('Checking /__whoami (no auth)')
try:
    r = s.get(f'{BASE}/__whoami', timeout=5)
    print('status', r.status_code)
    print(r.text)
except Exception as e:
    print('error', e)

print('\nAttempting login...')
try:
    r = s.post(f'{BASE}/login', data={'email': EMAIL, 'password': PASSWORD}, allow_redirects=True, timeout=5)
    print('login status', r.status_code)
    # fetch homepage
    r2 = s.get(f'{BASE}/', timeout=5)
    html = r2.text
    found = 'admin-top-link' in html
    print('admin-top-link in homepage HTML?', found)
    # print header-actions block for inspection
    start = html.find('<div class="header-actions">')
    if start != -1:
        print('\n--- header-actions snippet ---')
        print(html[start:start+400])
        print('--- end snippet ---\n')
    # check /__whoami with session
    r3 = s.get(f'{BASE}/__whoami', timeout=5)
    print('/__whoami (with session) status', r3.status_code)
    try:
        print(r3.json())
    except Exception:
        print(r3.text)
except Exception as e:
    print('login error', e)
