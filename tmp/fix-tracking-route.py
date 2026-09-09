from pathlib import Path
p=Path('tools/chrome-extension/background.js')
s=p.read_text(encoding='utf-8').replace('&& /\\/order\\//i.test(parsed.pathname)','&& (/\\/order\\//i.test(parsed.pathname) || parsed.pathname === "/myaccount/order-details")').replace('parsed.searchParams.get("orderId") === String(externalOrderId || "")','(parsed.searchParams.get("orderNumber") || parsed.searchParams.get("orderId")) === String(externalOrderId || "")').replace('new URL("https://www.homedepot.com/order/view/orderdetails")','new URL("https://www.homedepot.com/myaccount/purchase-history")')
p.write_text(s,encoding='utf-8')
p=Path('tools/chrome-extension/home-depot-checkout.js');s=p.read_text(encoding='utf-8')
s=s.replace('! /\\/order\\//i.test(url.pathname)','! /\\/order\\//i.test(url.pathname)')
s=s.replace('|| !/\\/order\\//i.test(url.pathname)', '|| !(/\\/order\\//i.test(url.pathname) || url.pathname === "/myaccount/order-details")')
s=s.replace('String(url.searchParams.get("orderId") || "").trim()', 'String(url.searchParams.get("orderNumber") || url.searchParams.get("orderId") || "").trim()')
needle='  const attempts = markedPoll ? 20 : 1;'
insert='''  if (markedPoll && location.pathname === "/myaccount/purchase-history") {
    const orderId = params.get("orderId");
    for (let attempt = 0; attempt < 20; attempt += 1) {
      const link = [...document.querySelectorAll("a[href]")].find(element => {
        const url = new URL(element.href, location.href);
        return url.hostname === "www.homedepot.com" && url.pathname === "/myaccount/order-details"
          && url.searchParams.get("orderNumber") === orderId;
      });
      if (link) {
        const target = new URL(link.href);
        target.searchParams.set("orderId", orderId);
        target.searchParams.set("autozs_tracking_poll", "1");
        target.searchParams.set("autozs_worker_opened_at", String(Date.now()));
        location.assign(target.href);
        return true;
      }
      await new Promise(resolve => setTimeout(resolve, 1000));
    }
  }
'''
s=s.replace(needle,insert+needle);p.write_text(s,encoding='utf-8')
