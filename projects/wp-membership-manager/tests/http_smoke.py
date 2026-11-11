"""Exercise installed WordPress admin forms and inspect actual Mailpit messages."""
import html
import http.cookiejar
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request

BASE = 'http://localhost:' + os.environ.get('WP_PORT', '8080')
MAIL = 'http://localhost:' + os.environ.get('MAILPIT_PORT', '8025')
jar = http.cookiejar.CookieJar()
client = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
checks = 0

def check(condition, message):
    global checks
    if not condition:
        raise AssertionError(message)
    checks += 1

def request(path, data=None, authenticated=True):
    opener = client if authenticated else urllib.request.build_opener()
    payload = urllib.parse.urlencode(data).encode() if data is not None else None
    try:
        response = opener.open(BASE + path, payload, timeout=20)
        return response.status, response.read().decode('utf-8', errors='replace')
    except urllib.error.HTTPError as error:
        return error.code, error.read().decode('utf-8', errors='replace')

# WordPress needs its test cookie before login.
request('/wp-login.php')
status, page = request('/wp-login.php', {'log':'demo','pwd':'local-demo-only','wp-submit':'Log In','redirect_to':BASE+'/wp-admin/admin.php?page=wpmm','testcookie':'1'})
check(status == 200 and 'Association overview' in page, 'Admin login/dashboard')
check('$2,250.00' in page and '$1,250.00' in page and '$1,000.00' in page, 'Sponsor totals rendered')
check('Renewals due within 30 days: 2 recipients' in page, 'Demo consent segment')
export_url = html.unescape(re.search(r'href="([^"]+)">Download summary CSV', page).group(1))
parts = urllib.parse.urlsplit(export_url)
export_path = parts.path + '?' + parts.query
status, summary = request(export_path)
check(status == 200 and 'members,5,count' in summary and 'alex@example.test' not in summary, 'Summary export contains totals without personal details')
status, _ = request(export_path, authenticated=False)
check(status != 200, 'Anonymous summary export rejected')
status, _ = request('/wp-admin/admin-post.php?action=wpmm_export_report&_wpnonce=bad')
check(status == 403, 'Summary export rejects invalid nonce')
nonce = re.search(r'name="_wpnonce" value="([^"]+)"', page).group(1)
campaign = re.search(r'name="campaign" value="([^"]+)"', page).group(1)
status, _ = request('/wp-admin/admin-post.php', {'action':'wpmm_save','task':'send','campaign':campaign,'_wpnonce':'bad'})
check(status == 403, 'Missing nonce rejected')
status, _ = request('/wp-admin/admin-post.php', {'action':'wpmm_save','task':'send','campaign':campaign,'_wpnonce':nonce}, authenticated=False)
check(status != 200, 'Anonymous mutation rejected')
status, page = request('/wp-admin/admin-post.php', {'action':'wpmm_save','task':'send','campaign':campaign,'_wpnonce':nonce})
check(status == 200 and '2 emails accepted' in page, 'Admin campaign send')
_, repeat = request('/wp-admin/admin-post.php', {'action':'wpmm_save','task':'send','campaign':campaign,'_wpnonce':nonce})
check('0 emails accepted' in repeat, 'Successful sends not duplicated')

with urllib.request.urlopen(MAIL+'/api/v1/messages', timeout=20) as response:
    inbox = json.load(response)
messages = [message for message in inbox['messages'] if message['Subject'] == 'Membership renewal reminder']
check(len(messages) == 2, 'Two real SMTP messages captured')
check({message['To'][0]['Address'] for message in messages} == {'alex@example.test','morgan@example.test'}, 'Mailpit recipients match consent segment')
with urllib.request.urlopen(MAIL+'/api/v1/message/'+messages[0]['ID'], timeout=20) as response:
    message = json.load(response)
html = message['HTML']
check('<h1>Your association membership</h1>' in html and '{{name}}' not in html, 'HTML and personalization arrived')
open_token = re.search(r'wpmm_open=([a-f0-9]{64})', html).group(1)
unsub_token = re.search(r'wpmm_unsubscribe=([a-f0-9]{64})', html).group(1)
status, _ = request('/?wpmm_open='+open_token, authenticated=False)
check(status == 200, 'Public open pixel')
request('/?wpmm_open='+open_token, authenticated=False)
status, page = request('/?wpmm_unsubscribe='+unsub_token, authenticated=False)
check(status == 200 and 'Confirm unsubscribe' in page, 'Unsubscribe requires confirmation')
_, before = request('/wp-admin/admin.php?page=wpmm')
check('Renewals due within 30 days: 2 recipients' in before, 'GET link does not unsubscribe')
status, page = request('/?wpmm_unsubscribe='+unsub_token, {'confirm':unsub_token}, authenticated=False)
check(status == 200 and 'You have been unsubscribed' in page, 'Unsubscribe confirmation persisted')
status, _ = request('/?wpmm_unsubscribe='+'a'*64, authenticated=False)
check(status == 404, 'Unknown token rejected')
_, page = request('/wp-admin/admin.php?page=wpmm')
check('Renewals due within 30 days: 1 recipients' in page, 'Dashboard reflects unsubscribe')
check(re.search(r'<dt>Unique recorded opens</dt><dd[^>]*>1</dd>',page) is not None, 'Repeated pixel counted once')
# Create and renew through the admin form, then register and import through HTTP.
common = {'action':'wpmm_save','_wpnonce':nonce}
_, page = request('/wp-admin/admin-post.php', dict(common, task='member',id='http1',name='<b>HTTP Example</b><script>alert(1)</script>',email='http@example.test',level='student',expires='2026-01-01',consent='no'))
check('http@example.test' in page and '<script>alert(1)</script>' not in page, 'Member form sanitizes and persists')
_, page = request('/wp-admin/admin-post.php', dict(common, task='renew',member='http1',receipt='http-receipt-1',amount='40.00'))
check('http-receipt-1' in page, 'Renewal form persists receipt')
_, page = request('/wp-admin/admin-post.php', dict(common, task='register',event='e1',member='http1'))
check('<td>http1</td>' in page, 'Registration form persisted')

boundary = 'wpmm-smoke-boundary'
csv = open(os.path.join(os.path.dirname(__file__),'../demo/salesforce-report.csv'),encoding='utf-8').read()
parts = []
for key,value in dict(common,task='import').items():
    parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{key}"\r\n\r\n{value}\r\n')
parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="csv"; filename="report.csv"\r\nContent-Type: text/csv\r\n\r\n{csv}\r\n--{boundary}--\r\n')
req = urllib.request.Request(BASE+'/wp-admin/admin-post.php', ''.join(parts).encode(), {'Content-Type':'multipart/form-data; boundary='+boundary})
# Fixture uses the same email as a seeded member, so the entire import must be rejected.
with client.open(req,timeout=20) as response:
    page = response.read().decode()
check('already belongs to another member ID' in page and '<td>003-demo-1</td>' not in page, 'CSV upload rejects conflicting external IDs atomically')
# Import supported contact and opportunity exports through the actual upload form.
def upload_sample(filename):
    with open(os.path.join(os.path.dirname(__file__), '../demo/', filename), encoding='utf-8') as sample:
        content = sample.read()
    fields = [f'--{boundary}\r\nContent-Disposition: form-data; name="{key}"\r\n\r\n{value}\r\n' for key,value in dict(common,task='import').items()]
    fields.append(f'--{boundary}\r\nContent-Disposition: form-data; name="csv"; filename="{filename}"\r\nContent-Type: text/csv\r\n\r\n{content}\r\n--{boundary}--\r\n')
    upload = urllib.request.Request(BASE+'/wp-admin/admin-post.php', ''.join(fields).encode(), {'Content-Type':'multipart/form-data; boundary='+boundary})
    with client.open(upload,timeout=20) as response:
        return response.read().decode()
page = upload_sample('salesforce-contacts.csv')
check('2 report rows imported' in page and '<td>003-export-1</td>' in page, 'Contact export upload')
page = upload_sample('salesforce-opportunities.csv')
check('1 report rows imported' in page and '$4,250.00' in page and '$2,500.00' in page, 'Opportunity export updates dashboard totals')
page = upload_sample('salesforce-opportunities.csv')
check('$4,250.00' in page and '$6,250.00' not in page, 'Repeated opportunity import is an update')
# Stripe webhook endpoint: unsigned requests are refused; a correctly signed event for a payment this site does not hold is acknowledged and changes nothing.
import hashlib, hmac, time
def webhook(body, signature=None):
    headers = {'Content-Type': 'application/json'}
    if signature is not None:
        headers['Stripe-Signature'] = signature
    hook = urllib.request.Request(BASE+'/wp-admin/admin-post.php?action=wpmm_stripe_webhook', body.encode(), headers)
    try:
        with urllib.request.build_opener().open(hook, timeout=20) as response:
            return response.status
    except urllib.error.HTTPError as error:
        return error.code
secret = os.environ.get('WPMM_STRIPE_WEBHOOK_SECRET', 'whsec_local_demo_only')
event = json.dumps({'id':'evt_smoke','object':'event','type':'checkout.session.expired','data':{'object':{'id':'cs_smoke','object':'checkout.session','metadata':{'payment_id':'000000000000000000000000'},'payment_status':'unpaid','status':'expired'}}})
stamp = int(time.time())
good = f"t={stamp},v1=" + hmac.new(secret.encode(), f"{stamp}.{event}".encode(), hashlib.sha256).hexdigest()
check(webhook(event) == 400, 'Webhook without a Stripe signature rejected')
check(webhook(event, f"t={stamp},v1=0000") == 400, 'Webhook with a forged signature rejected')
check(webhook(event, good) == 200, 'Correctly signed webhook acknowledged')
print(f'{checks} HTTP/Mailpit checks passed.')
