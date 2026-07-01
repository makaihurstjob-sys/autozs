import argparse
import json
import re
import sys
from pathlib import Path
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
PROFILE_DIR = ROOT / ".browser-profile" / "home-depot"
CHROME_PROFILE_DIR = ROOT / ".browser-profile" / "home-depot-chrome"


CAPTURE_JS = r"""
() => {
  const clean = value => String(value || '').replace(/\s+/g, ' ').trim();
  const uniq = values => [...new Set(values.filter(Boolean).map(clean).filter(Boolean))];
  const visibleText = document.body.innerText || '';
  const jsonProducts = [];
  document.querySelectorAll('script[type="application/ld+json"]').forEach(script => {
    try {
      const parsed = JSON.parse(script.textContent);
      const queue = Array.isArray(parsed) ? [...parsed] : [parsed];
      while (queue.length) {
        const item = queue.shift();
        if (!item || typeof item !== 'object') continue;
        const type = item['@type'];
        if (type === 'Product' || (Array.isArray(type) && type.includes('Product'))) jsonProducts.push(item);
        Object.values(item).forEach(value => {
          if (value && typeof value === 'object') Array.isArray(value) ? queue.push(...value) : queue.push(value);
        });
      }
    } catch {}
  });
  const productJson = jsonProducts[0] || {};
  const offer = Array.isArray(productJson.offers) ? productJson.offers[0] : productJson.offers || {};
  const parsePrice = value => {
    const text = clean(value);
    if (!text) return null;
    const explicit = text.match(/\$\s*([0-9]{1,4}(?:,[0-9]{3})*)(?:\s*[.]\s*|\s+)([0-9]{2})\b/) || text.match(/\$\s*([0-9]{1,4}(?:,[0-9]{3})*)(?:\.([0-9]{2}))?/);
    if (!explicit) return null;
    const parsed = Number(explicit[1].replace(/,/g, '') + '.' + (explicit[2] || '00'));
    return parsed > 0 && parsed < 10000 ? parsed : null;
  };
  const prices = [];
  const addPrice = value => {
    const parsed = parsePrice(value);
    if (parsed) prices.push(parsed);
  };
  addPrice(offer.price);
  document.querySelectorAll('meta[property="product:price:amount"], meta[name="product:price:amount"], meta[itemprop="price"], [itemprop="price"]').forEach(el => {
    addPrice(el.content || el.getAttribute('content') || el.getAttribute('value') || el.textContent);
  });
  document.querySelectorAll('[data-testid*="price" i], [class*="price" i], [id*="price" i], [aria-label*="price" i], [data-automation-id*="price" i]').forEach(el => {
    addPrice(el.innerText || el.textContent || el.getAttribute('aria-label') || el.getAttribute('content') || el.getAttribute('value'));
    Object.values(el.dataset || {}).forEach(addPrice);
  });
  (visibleText.match(/\$\s*[0-9]{1,4}(?:,[0-9]{3})*(?:\s*[.]\s*|\s+)?[0-9]{0,2}/g) || []).slice(0, 30).forEach(addPrice);

  const imageCandidates = [];
  document.querySelectorAll('meta[property="og:image"], meta[name="og:image"]').forEach(meta => imageCandidates.push(meta.content));
  const structuredImages = productJson.image ? (Array.isArray(productJson.image) ? productJson.image : [productJson.image]) : [];
  imageCandidates.push(...structuredImages);
  [...document.images].forEach(img => {
    imageCandidates.push(img.currentSrc, img.src, img.dataset.src, img.dataset.zoom, img.dataset.image, img.dataset.imageUrl);
    imageCandidates.push(...Object.values(img.dataset || {}));
    if (img.srcset) img.srcset.split(',').forEach(part => imageCandidates.push(part.trim().split(/\s+/)[0]));
  });
  const rawHtml = document.documentElement.innerHTML.replace(/\\u002F/g, '/');
  const htmlImages = rawHtml.match(/https?:\/\/[^"'\\\s<>]+?\.(?:jpg|jpeg|png|webp)(?:\?[^"'\\\s<>]*)?/gi) || [];
  imageCandidates.push(...htmlImages.map(src => src.replace(/&amp;/g, '&')));
  const images = uniq(imageCandidates.map(src => {
    try { return new URL(src, location.href).href; } catch { return ''; }
  })).filter(src => /\.(jpg|jpeg|png|webp)(\?|$)/i.test(src) || src.startsWith('data:image/')).slice(0, 100);

  const bulletText = [];
  [
    '[data-testid*="bullet"] li',
    '[data-testid*="product-overview"] li',
    '[class*="product-overview"] li',
    '[class*="ProductOverview"] li',
    '.bullet-list li',
    'li'
  ].forEach(selector => document.querySelectorAll(selector).forEach(el => {
    const text = clean(el.innerText);
    if (text.length >= 12 && text.length <= 220 && !/sponsored|advertisement|sign in/i.test(text)) bulletText.push(text);
  }));
  const bullets = uniq(bulletText).slice(0, 12);
  const metaDescription = document.querySelector('meta[name="description"]')?.content || document.querySelector('meta[property="og:description"]')?.content || '';

  return {
    source_url: location.href,
    title: clean(productJson.name || document.querySelector('h1')?.innerText || document.querySelector('meta[property="og:title"]')?.content || document.title),
    source_price: prices[0] || null,
    description: bullets.length ? bullets.join('\n') : clean(productJson.description || metaDescription),
    image_urls: images.join('\n')
  };
}
"""


def number_or_none(value: str | None) -> float | None:
    if value is None or not value.strip():
        return None
    cleaned = re.sub(r"[^0-9.]", "", value)
    return float(cleaned) if cleaned else None


def post_json(url: str, payload: dict) -> dict:
    request = Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urlopen(request, timeout=20) as response:
        return json.loads(response.read().decode("utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser(description="Capture Home Depot product data through a persistent browser session.")
    parser.add_argument("urls", nargs="+", help="Home Depot product URL(s) to capture")
    parser.add_argument("--api", default="http://127.0.0.1:8000", help="Local API base URL")
    parser.add_argument("--shipping", type=float, default=None, help="Source shipping cost to attach to every captured product")
    parser.add_argument("--competitor", type=float, default=None, help="Competitor/eBay price to attach to every captured product")
    parser.add_argument("--proxy-server", default=None, help="Optional proxy, e.g. http://user:pass@host:port")
    parser.add_argument(
        "--browser-channel",
        choices=["chromium", "chrome"],
        default="chromium",
        help="Use Playwright Chromium or the installed Google Chrome channel.",
    )
    parser.add_argument("--executable-path", default=None, help="Optional browser executable path.")
    parser.add_argument("--headless", action="store_true", help="Run browser headless. Visible browser is usually less likely to be blocked.")
    parser.add_argument("--pause", action="store_true", help="Pause after opening each URL so you can solve location/captcha prompts.")
    args = parser.parse_args()

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("Playwright is not installed. Run:", file=sys.stderr)
        print(f"{sys.executable} -m pip install -r apps/api/requirements-browser.txt", file=sys.stderr)
        print(f"{sys.executable} -m playwright install chromium", file=sys.stderr)
        return 2

    profile_dir = CHROME_PROFILE_DIR if args.browser_channel == "chrome" else PROFILE_DIR
    profile_dir.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as playwright:
        launch_options = {
            "headless": args.headless,
            "viewport": {"width": 1440, "height": 1000},
            "locale": "en-US",
            "args": [
                "--disable-blink-features=AutomationControlled",
                "--no-first-run",
                "--no-default-browser-check",
            ],
        }
        if args.browser_channel == "chrome":
            launch_options["channel"] = "chrome"
        if args.executable_path:
            launch_options["executable_path"] = args.executable_path
        if args.proxy_server:
            launch_options["proxy"] = {"server": args.proxy_server}
        context = playwright.chromium.launch_persistent_context(str(profile_dir), **launch_options)
        page = context.pages[0] if context.pages else context.new_page()
        for source_url in args.urls:
            print(f"Opening {source_url}")
            page.goto(source_url, wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(3500)
            if args.pause:
                input("Review the browser, solve any prompts, then press Enter to capture...")
            payload = page.evaluate(CAPTURE_JS)
            if args.shipping is not None:
                payload["source_shipping"] = args.shipping
            if args.competitor is not None:
                payload["competitor_price"] = args.competitor
            if payload.get("source_price") is None and sys.stdin.isatty():
                payload["source_price"] = number_or_none(input("Source price was not detected. Enter it or leave blank: "))
            result = post_json(f"{args.api.rstrip('/')}/products/import-captured", payload)
            print(f"Imported {result['sku']}: source={payload.get('source_price')} title={result['title'][:80]}")
        context.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
