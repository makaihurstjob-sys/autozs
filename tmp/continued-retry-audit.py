import json,re,urllib.request
from pathlib import Path
a=json.loads(Path('tmp/resumed-batch-audit.json').read_text())
links=[]
for file in ['continued-active.json','continued-active-page2.json','continued-scheduled-after-hose.json']:
 d=json.loads(Path('tmp/'+file).read_text(encoding='utf-16'))['value']
 links += [v for v in d['links'] if v['text']]
def norm(s):return re.sub(r'[^a-z0-9]','',s.lower().replace('free shipping',''))
print('Inventory titles',len(links))
for p in a['products']:
 if p['jobs'] and p['jobs'][0]['status']=='needs_review' and p['product_id']!=104:
  pkg=json.load(urllib.request.urlopen(f"http://127.0.0.1:8000/products/{p['product_id']}/ebay-package"))
  matches=[v for v in links if norm(v['text'])==norm(pkg['title'])]
  print(json.dumps({'product':p['product_id'],'job':p['jobs'][0]['id'],'title':pkg['title'],'specifics':pkg['item_specifics'],'matches':matches,'reason':p['jobs'][0]['message'][:180]}))

