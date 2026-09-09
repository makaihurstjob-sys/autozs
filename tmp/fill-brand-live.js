(async()=>{if(await hasRunningListingJob())throw Error("Job running");const t=(await chrome.tabs.query({url:"https://www.ebay.com/lstng*"}))[0];return await chrome.scripting.executeScript({target:{tabId:t.id},func:async()=>{try{function itemSpecificMatches(key, value) {
  const expectedKey = normalizeText(key);
  const expectedValue = normalizeComparableValue(value);
  if (!expectedKey || !expectedValue) return false;
  const controls = [...document.querySelectorAll('button[name^="attributes."], input, textarea')].filter(isVisible);
  return controls.some((element) => {
    if (/search-box|extracted-attribute-selector/i.test(element.getAttribute("name") || "")) return false;
    const label = normalizeText([
      element.id,
      element.getAttribute("name"),
      element.getAttribute("aria-label"),
      element.getAttribute("data-testid"),
      labelText(element),
    ].filter(Boolean).join(" "));
    const current = normalizeComparableValue(element.value || element.innerText || element.textContent || "");
    return Boolean(current) && label.includes(expectedKey) && (current === expectedValue);
  });
}
async function fillEbayItemSpecificRow(row, expected) {
  if (itemSpecificMatches(row.key, expected)) return true;
  const trigger = [...row.valueHost.querySelectorAll('button[aria-controls]')].find(isVisible);
  if (!trigger) return false;
  if (trigger.getAttribute('aria-expanded') !== 'true') trigger.click();
  await waitForCondition(() => Boolean(ebayItemSpecificOptionPanel(trigger)), 3000, 150);
  const panel = ebayItemSpecificOptionPanel(trigger);
  if (!panel) return false;
  const input = [...panel.querySelectorAll('input[type="text"]')].find(isVisible);
  if (input) {
    await setEbayTextFieldValue(input, expected);
    await delay(500);
  }
  const option = [...panel.querySelectorAll('[role="menuitemcheckbox"], [role="menuitemradio"], [role="option"], [role="menuitem"], button')]
    .filter(isVisible).find((candidate) => itemSpecificOptionMatches(candidate, expected));
  if (option && option.getAttribute('aria-checked') !== 'true') option.click();
  await delay(400);
  if (trigger.getAttribute('aria-expanded') === 'true') trigger.click();
  await delay(250);
  return itemSpecificMatches(row.key, expected);
}
if(!location.href.includes("mode=ReviseItem")||!location.href.includes("draftId=5167880600803") || document.querySelector('input[name="title"]')?.value!=="5/8 in. x 50 ft. Heavy-Duty Hose | FREE SHIPPING")throw Error("Wrong item");
const row=ebayItemSpecificRows().find(r=>r.key==="Brand");return {filled:await fillEbayItemSpecificRow(row,"Husky"),brand:document.querySelector('button[name="attributes.Brand"]')?.innerText};
}catch(e){return {error:String(e)}}}});})()