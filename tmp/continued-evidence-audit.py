import json,sqlite3,re,collections,urllib.request
from pathlib import Path
def read(path):
 b=Path(path).read_bytes();return json.loads(b.decode('utf-16' if b.startswith((b'\xff\xfe',b'\xfe\xff')) else 'utf-8-sig'))
def norm(s):return re.sub('[^a-z0-9]','',s.lower().replace('free shipping',''))
evidence={}
for name in ['continued-active.json','continued-active-page2.json','continued-scheduled-after-hose.json','final-active-page1.json','final-active-page2.json','final-scheduled.json']:
 p=Path('tmp')/name
 if not p.exists():continue
 data=read(p)['value']
 for link in data['links']:
  match=re.search('/itm/([0-9]{12})',link['url'])
  if match and link['text']: evidence[match[1]]={'title':link['text'],'file':name}
for path in Path('tmp').glob('confirmed-*.json'):
 d=read(path)
 if d.get('confirmation') and d.get('itemId'):
  title=re.search(r'Your listing has been (?:scheduled|listed|revised)\n([^\n]+)',d['text'])
  if title:evidence[d['itemId']]={'title':title[1],'file':path.name}
for name in ['melnor-final-attempt.json','hose-revised-confirmation.json']:
 data=read(Path('tmp')/name)['value'];text=data['text'];item=re.search(r'ID-([0-9]{12})',text);title=re.search(r'Your listing has been (?:scheduled|listed|revised)\n([^\n]+)',text)
 if item and title:evidence[item[1]]={'title':title[1],'file':name}
c=sqlite3.connect('file:C:/AutoZS/data/autozs.db?mode=ro',uri=True);c.row_factory=sqlite3.Row
batch=read('tmp/verified-ready-batch-2026-09-07.json')['value']['products'];out=[]
for p in batch:
 job=c.execute('select * from listing_jobs where product_id=? order by id desc',(p['id'],)).fetchone()
 r={'product':p['id'],'status':job['status'] if job else 'no_job'}
 if job:
  r.update(job=job['id'],message=job['message'])
  if job['status']=='completed':
   item=re.search(r'item ([0-9]{12})',job['message'] or '')
   if item:
    r['item']=item[1];r['evidence']=evidence.get(item[1]);
    if r['evidence']:
     pkg=json.load(urllib.request.urlopen(f"http://127.0.0.1:8000/products/{p['id']}/ebay-package"))
     r['title_matches']=norm(pkg['title'])==norm(r['evidence']['title'])
     r['identity_matches']=r['title_matches']
     if p['id']==209 and norm(r['evidence']['title'])==norm('to the Roots '+pkg['title']):
      r['identity_matches']=True
      r['title_note']='Existing eBay title retains the legacy partial brand prefix to the Roots; remaining product title matches exactly.'
 out.append(r)
Path('tmp/continued-evidence-audit.json').write_text(json.dumps(out,indent=2))
print('Batch states:',dict(collections.Counter(r['status'] for r in out)))
complete=[r for r in out if r['status']=='completed'];verified=[r for r in complete if r.get('identity_matches')]
print('Completed with matching eBay product identity+ID evidence:',len(verified),'of',len(complete))
for r in complete:
 if not r.get('identity_matches'):print(json.dumps(r))
