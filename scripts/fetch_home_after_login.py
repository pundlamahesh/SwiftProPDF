import requests

session = requests.Session()
login_url = 'http://127.0.0.1:5000/login'
home_url = 'http://127.0.0.1:5000/'

resp = session.post(login_url, data={'email': 'test@example.com', 'password': 'password123'})
print('Login status:', resp.status_code)
home = session.get(home_url)
print('Home length:', len(home.text))
print(home.text[:800])
