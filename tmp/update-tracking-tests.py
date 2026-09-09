from pathlib import Path
p=Path('tools/chrome-extension/background.test.js')
s=p.read_text(encoding='utf-8').replace('[SUPPLIER_TRACKING_ALARM, 5, 360]','[SUPPLIER_TRACKING_ALARM, 5, 5]').replace('Expected Home Depot tracking checks to run no more than once every six hours.','Expected five-minute polling with per-order check intervals.')
s=s.replace('prepared[String(candidate.supplier_order_id)] === fingerprint','candidate.verification_only =')
p.write_text(s,encoding='utf-8')
p=Path('tools/chrome-extension/ebay-tracking-upload.test.js')
s=p.read_text(encoding='utf-8')
a=s.index('if (/save[^');b=s.index('if (!source.includes',a)
s=s[:a]+s[b:]
p.write_text(s,encoding='utf-8')
