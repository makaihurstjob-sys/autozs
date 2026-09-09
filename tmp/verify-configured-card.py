import sys,json
sys.path.insert(0,'C:/AutoZS/repo/apps/api')
from app.services.windows_credentials import read_supplier_payment_credential
c=read_supplier_payment_credential('home_depot')
print(json.dumps({'configured_card_last_four':c['card_number'][-4:]}))
