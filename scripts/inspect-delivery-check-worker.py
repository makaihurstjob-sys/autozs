"""Install/check only the dedicated extension; supplier reads go through that extension."""
import argparse
import json
from pathlib import Path
import time
from playwright.sync_api import sync_playwright

parser = argparse.ArgumentParser()
parser.add_argument('--port', type=int, default=9335)
parser.add_argument('--inspect-cart', action='store_true')
parser.add_argument('--reload', action='store_true')
parser.add_argument('--inspect-product')
args = parser.parse_args()
extension = Path(__file__).resolve().parents[1] / 'tmp' / 'delivery-check-extension'


def ready_worker(context, timeout=15):
    """A serviceworker event can arrive before Chrome installs extension APIs."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        for candidate in context.service_workers:
            if not candidate.url.endswith('/background.js'):
                continue
            try:
                name = candidate.evaluate("() => globalThis.chrome?.runtime?.getManifest?.().name")
                if name == 'AutoZS Isolated Delivery Checks':
                    return candidate
            except Exception:
                # A replaced worker may remain in Playwright's list briefly.
                continue
        time.sleep(0.2)
    raise RuntimeError('The isolated delivery extension did not become ready')


with sync_playwright() as p:
    browser = p.chromium.connect_over_cdp(f'http://127.0.0.1:{args.port}', timeout=15000)
    cdp = browser.new_browser_cdp_session()
    context = browser.contexts[0]
    worker = next((w for w in context.service_workers if w.url.endswith('/background.js')), None)
    if worker is None:
        with context.expect_event('serviceworker', predicate=lambda w: w.url.endswith('/background.js'), timeout=15000) as event:
            cdp.send('Extensions.loadUnpacked', {'path': str(extension)})
        event.value
        worker = ready_worker(context)
    if worker.evaluate('() => chrome.runtime.getManifest().name') != 'AutoZS Isolated Delivery Checks':
        raise RuntimeError('Expected the isolated delivery extension')
    if args.reload:
        if worker.evaluate("async () => Boolean((await chrome.storage.local.get('deliveryCheckState')).deliveryCheckState?.job)"):
            raise RuntimeError('An existing check must not be interrupted for reload')
        with context.expect_event('serviceworker', predicate=lambda w: w.url.endswith('/background.js'), timeout=15000) as event:
            cdp.send('Extensions.loadUnpacked', {'path': str(extension)})
        event.value
        worker = ready_worker(context)
    print(json.dumps(worker.evaluate("async () => {const s=(await chrome.storage.local.get('deliveryCheckState')).deliveryCheckState; return {name:chrome.runtime.getManifest().name, phase:s?.phase||null, paused:!!s?.paused, message:s?.message||null};}")))
    if args.inspect_cart or args.inspect_product:
        from urllib.parse import urlparse
        import re
        target_url = args.inspect_product or 'https://www.homedepot.com/mycart/home'
        if args.inspect_product:
            parsed = urlparse(target_url)
            if parsed.scheme != 'https' or parsed.netloc != 'www.homedepot.com' or not re.fullmatch(r'/p/[^/]+/\d+/?', parsed.path):
                raise ValueError('Expected a Home Depot product URL')
        tab_id = worker.evaluate("""async url => {
          const state = (await chrome.storage.local.get('deliveryCheckState')).deliveryCheckState;
          if (state) throw Error('An existing delivery check must not be interrupted');
          await chrome.storage.local.set({deliveryInspectionUntil:Date.now()+60000});
          await chrome.alarms.clear('delivery-check');
          return (await chrome.tabs.create({url,active:false})).id;
        }""", target_url)
        try:
            time.sleep(15)
            print(json.dumps(worker.evaluate("""async tabId => {
              const results = await chrome.scripting.executeScript({target:{tabId},func:() => ({
                path:location.pathname,
                title:document.title,
                pageNotice:document.body.innerText.slice(0,300),
                empty:/your cart is empty|there['’]s nothing in here yet/i.test(document.body.innerText),
                verification:/verify you are human|pardon our dust|access denied/i.test(document.body.innerText),
                buttons:[...document.querySelectorAll('button,[role="button"],a')].filter(e=>e.getClientRects().length && /sign in|my account|deliver|zip|add to cart|cart/i.test(e.innerText || e.getAttribute('aria-label') || '')).map(e=>({text:e.innerText,aria:e.getAttribute('aria-label'),testid:e.getAttribute('data-testid')})).slice(0,20),
                cartCount:document.querySelector('[data-testid="header-cart-count"]')?.textContent ?? null,
                inputs:[...document.querySelectorAll('input')].filter(e=>e.getClientRects().length).map(e=>({name:e.name,id:e.id,aria:e.getAttribute('aria-label'),testid:e.getAttribute('data-testid')}))
              })}); return results.map(r=>r.result);
            }""", tab_id)))
        finally:
            worker.evaluate("""async tabId => {
              await chrome.tabs.remove(tabId);
              await chrome.storage.local.set({deliveryInspectionUntil:0});
              await chrome.alarms.create('delivery-check',{periodInMinutes:0.5});
            }""", tab_id)
