def test_depop_capture_is_not_an_unfinished_ebay_draft(client):
    product = client.post('/products/import-captured', json={
        'source_url':'https://www.amazon.com/dp/B012345678', 'title':'Canvas bag',
        'source_price':20, 'description':'Canvas bag with adjustable strap.'}).json()
    identity=product['id']
    assert identity in {r['product_id'] for r in client.get('/products/capture-queue').json()['items']}
    response=client.post('/depop/amazon-import',json={'product_id':identity,'title':'Canvas bag','price':20,
        'variations':[{'label':'Black','asin':'B012345678','image_url':'https://images.test/bag.jpg'}]})
    assert response.status_code==200,response.text
    assert identity not in {r['product_id'] for r in client.get('/products/capture-queue').json()['items']}
    assert client.post('/products/capture-queue/claim',json={'worker_id':'capture-worker'}).json() is None


def test_uncaptured_phone_draft_still_queues(client):
    response=client.post('/products/phone-import',json={'source_url':'https://www.homedepot.com/p/Uncaptured-Phone-Draft/123456789'})
    assert response.status_code==200,response.text
    identity=response.json()['product_id']
    assert identity in {r['product_id'] for r in client.get('/products/capture-queue').json()['items']}
