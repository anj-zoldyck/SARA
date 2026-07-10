from django.test import Client
from accounts.models import User
c = Client()
c.force_login(User.objects.filter(role='MSWDO').first())
r = c.get('/mswdo/map/')
content = r.content.decode('utf-8')
import re
match = re.search(r'const weatherRisks = JSON\.parse\(\'(.*?)\'\);', content)
if match:
    print('MATCH:', match.group(1))
else:
    print('No match')
print('CONTENT:', [line.strip() for line in content.split('\n') if 'weatherRisks' in line])
print('FETCHED_AT:', [line.strip() for line in content.split('\n') if 'weatherFetchedAt' in line])
