var API = "https://desktop-56u49jf.tailb2892a.ts.net:8443";
var DASHBOARD = "https://desktop-56u49jf.tailb2892a.ts.net/?api=https://desktop-56u49jf.tailb2892a.ts.net:8443";
var CAPTURE_BUILD = "2026-07-28-ebay-account-detection-guard";
var AUTOZS_WORKER_MODE_KEY = "autozsWorkerMode";

function defaultAutozsWorkerMode() {
  const platform = String(
    globalThis.navigator?.userAgentData?.platform ||
    globalThis.navigator?.platform ||
    globalThis.navigator?.userAgent ||
    ""
  );
  return /\bWin|Windows\b/i.test(platform) ? "operations" : "viewer";
}

async function readAutozsWorkerMode() {
  try {
    const stored = await chrome.storage.local.get(AUTOZS_WORKER_MODE_KEY);
    const mode = stored?.[AUTOZS_WORKER_MODE_KEY];
    return mode === "operations" || mode === "viewer" ? mode : defaultAutozsWorkerMode();
  } catch {
    return defaultAutozsWorkerMode();
  }
}

function numberOrNull(value) {
  const cleaned = String(value || "").replace(/[^0-9.]/g, "");
  return cleaned ? Number(cleaned) : null;
}

function fallbackTheme() {
  return window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

async function readAppTheme() {
  try {
    const response = await fetch(`${API}/settings`, { cache: "no-store" });
    if (!response.ok) throw new Error(`settings returned ${response.status}`);
    const settings = await response.json();
    return settings.ui_theme === "dark" || settings.ui_theme === "light" ? settings.ui_theme : fallbackTheme();
  } catch {
    return fallbackTheme();
  }
}

async function checkLocalApi() {
  const response = await fetch(`${API}/health`, { cache: "no-store" });
  if (!response.ok) throw new Error(`API returned ${response.status}`);
  return response.json();
}

function sourceRefreshContextFromLocation() {
  try {
    const params = new URLSearchParams(location.search);
    const jobId = Number(params.get("autozs_refresh_job"));
    const batchKey = params.get("autozs_refresh_batch") || "";
    return jobId && batchKey ? { jobId, batchKey } : null;
  } catch {
    return null;
  }
}

async function failSourceRefreshJob(jobId, message) {
  const response = await fetch(`${API}/source-refresh/jobs/${jobId}/failed`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message: String(message || "Browser capture failed") }),
  });
  if (!response.ok) throw new Error(await response.text());
  return response.json();
}

async function claimNextSourceRefreshJob(batchKey) {
  const response = await fetch(`${API}/source-refresh/batches/${encodeURIComponent(batchKey)}/next`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
  });
  if (!response.ok) throw new Error(await response.text());
  return response.json();
}

function detectEbaySignedInUsernameFromPage() {
  const clean = (value) => String(value || "").replace(/\s+/g, " ").trim();
  const usernamePattern = /^[A-Za-z0-9._-]{2,64}$/;
  const ignoredUsernameCandidates = new Set(["account", "kg", "lb", "lbs", "oz", "stand", "user"]);
  const usernameLike = (value) => /[._-]|\d/.test(value || "");
  const cleanUsername = (value) => {
    const text = clean(value)
      .replace(/\([^)]*\)/g, " ")
      .replace(/[!,:;]+$/g, "")
      .trim();
    return usernamePattern.test(text) && !ignoredUsernameCandidates.has(text.toLowerCase()) ? text : "";
  };
  const usernameFromText = (value, allowPlain = false, allowFallback = false) => {
    const text = clean(value);
    if (!text || /sign in|register|guest|help|cart|watchlist|my ebay/i.test(text)) return "";
    const profileMatch = text.match(/\b([A-Za-z0-9._-]{2,64})\s*\([^)]*(?:feedback|\d)/i);
    if (profileMatch) return cleanUsername(profileMatch[1]);
    if (allowFallback) {
      const userLine = text
        .split(/\s*[|\n]\s*/)
        .map(cleanUsername)
        .find((candidate) => candidate && (allowPlain || usernameLike(candidate)));
      if (userLine) return userLine;
    }
    const hiMatch = text.match(/\bHi[, ]+([A-Za-z0-9._-]{2,64})\b/i);
    if (hiMatch && usernameLike(hiMatch[1])) return cleanUsername(hiMatch[1]);
    const signedInMatch = text.match(/\b(?:signed in as|account|username|user id)[: ]+([A-Za-z0-9._-]{2,64})\b/i);
    if (signedInMatch) return cleanUsername(signedInMatch[1]);
    const fallback = cleanUsername(text);
    return allowFallback && fallback && (allowPlain || usernameLike(fallback)) ? fallback : "";
  };
  const candidates = [];
  const addCandidate = (value, priority, allowPlain = false, allowFallback = false) => {
    const username = usernameFromText(value, allowPlain, allowFallback);
    if (!username) return;
    candidates.push({ username, priority: priority + (usernameLike(username) ? 10 : 0) });
  };
  const selectors = [
    "#gh-ug",
    "#gh-eb-uid",
    "[data-testid*='user' i]",
    "[data-testid*='account' i]",
    "[aria-label*='account' i]",
    "[aria-label*='user' i]",
    "[title*='account' i]",
    "[title*='user' i]",
    "a[href*='/usr/']",
    "a[href*='feedback_profile']",
  ];
  document.querySelectorAll(selectors.join(",")).forEach((element) => {
    const href = element.getAttribute("href") || "";
    const elementId = element.getAttribute("id") || element.id || "";
    const profileMatch = href.match(/(?:\/usr\/|feedback_profile\/)([A-Za-z0-9._-]{2,64})/i);
    if (profileMatch) addCandidate(profileMatch[1], 100, true, true);
    const hasProfileHref = /\/usr\/|feedback_profile/i.test(href);
    const trustedAccountChrome = hasProfileHref || ["gh-ug", "gh-eb-uid"].includes(elementId);
    addCandidate(
      element.getAttribute("aria-label"),
      hasProfileHref ? 90 : 45,
      trustedAccountChrome,
      trustedAccountChrome
    );
    addCandidate(
      element.getAttribute("title"),
      hasProfileHref ? 90 : 45,
      trustedAccountChrome,
      trustedAccountChrome
    );
    addCandidate(
      element.textContent,
      hasProfileHref ? 90 : 45,
      trustedAccountChrome,
      trustedAccountChrome
    );
  });
  const bodyRaw = String(document.body?.innerText || "");
  const bodyText = clean(bodyRaw);
  bodyRaw.split(/\n+/).forEach((line) => {
    if (/\([^)]*(?:feedback|\d)/i.test(line)) addCandidate(line, 30);
  });
  const bodyHiMatch = bodyText.match(/\bHi[, ]+([A-Za-z0-9._-]{2,64})\b/i);
  if (bodyHiMatch && usernameLike(bodyHiMatch[1])) addCandidate(bodyHiMatch[1], 5, false, true);
  candidates.sort((left, right) => right.priority - left.priority);
  return candidates[0]?.username || "";
}

async function reportEbayBrowserAccount(accountKey = "manual") {
  const username = detectEbaySignedInUsernameFromPage();
  if (!username) {
    const query = accountKey ? `?account_key=${encodeURIComponent(accountKey)}` : "";
    const fallbackResponse = await fetch(`${API}/ebay/browser-account${query}`, { cache: "no-store" });
    if (!fallbackResponse.ok) throw new Error(await fallbackResponse.text());
    return fallbackResponse.json();
  }
  const response = await fetch(`${API}/ebay/browser-account`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      detected_username: username || null,
      url: location.href,
      marketplace: location.hostname.endsWith("ebay.com") ? "EBAY_US" : "",
      source: "chrome-extension",
      account_key: accountKey || "manual",
    }),
  });
  if (!response.ok) throw new Error(await response.text());
  return response.json();
}

function isEbayPage() {
  return typeof location !== "undefined" && /^www\.ebay\.(com|co\.uk|ca|com\.au)$|^sell\.ebay\.com$/i.test(location.hostname || "");
}

function autozsAccountKeyFromLocation() {
  try {
    const search = String(location.search || "").replace(/^\?/, "");
    const hash = String(location.hash || "").replace(/^#/, "");
    const params = new URLSearchParams([search, hash].filter(Boolean).join("&"));
    return params.get("autozs_account_key") || "manual";
  } catch {
    return "manual";
  }
}

function autozsParamsFromLocation() {
  try {
    const search = String(location.search || "").replace(/^\?/, "");
    const hash = String(location.hash || "").replace(/^#/, "");
    return new URLSearchParams([search, hash].filter(Boolean).join("&"));
  } catch {
    return new URLSearchParams();
  }
}

function startEbayBrowserAccountReporter() {
  if (!isEbayPage() || window.__autozsEbayBrowserAccountReporterStarted) return;
  window.__autozsEbayBrowserAccountReporterStarted = true;
  const report = () => reportEbayBrowserAccount(autozsAccountKeyFromLocation()).catch(() => {});
  [750, 2500, 6000].forEach((delay) => setTimeout(report, delay));
  document.addEventListener("visibilitychange", () => {
    if (!document.hidden) setTimeout(report, 250);
  });
  window.addEventListener("pageshow", () => setTimeout(report, 250));
}

function detectEbayDraftPresence() {
  const params = autozsParamsFromLocation();
  const draftId = params.get("draftId") || params.get("draft_id") || "";
  const reconcileRequested = params.get("autozs_reconcile_listing") === "1";
  const text = String(document.body?.innerText || "").replace(/\s+/g, " ").trim();
  const normalized = text.toLowerCase();
  const missing =
    /this listing is no longer available|listing not found|draft not found|page not found|we looked everywhere|can't find|cannot find|no longer exists|invalid draft/i.test(text);
  const present =
    /complete your listing|photos|title|item specifics|pricing|delivery|shipping|save for later|list it/i.test(text) &&
    (/\/lstng/i.test(location.pathname || "") || Boolean(draftId));
  if (missing) return { exists: false, draftId, message: "eBay reported this draft or listing could not be found." };
  if (present && reconcileRequested) {
    return { exists: true, draftId, message: `Opened and reconciled eBay draft ${draftId || "unknown"}.` };
  }
  if (present) return { exists: null, draftId, message: "eBay opened a listing editor, but Seller Hub Drafts must confirm the saved draft still exists." };
  if (normalized.includes("sign in")) return { exists: null, draftId, message: "eBay sign-in is required before draft verification." };
  return { exists: null, draftId, message: "Waiting for eBay draft verification page." };
}

function normalizeDraftTitle(value) {
  return String(value || "")
    .toLowerCase()
    .replace(/\bfree shipping\b/g, "")
    .replace(/[^a-z0-9]+/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

function ebayDraftListHaystack() {
  const text = String(document.body?.innerText || "");
  const links = Array.from(document.querySelectorAll("a[href], button, input, [data-testid]"))
    .map((element) => [
      element.getAttribute?.("href"),
      element.getAttribute?.("aria-label"),
      element.getAttribute?.("title"),
      element.getAttribute?.("value"),
      element.textContent,
    ].filter(Boolean).join(" "))
    .join(" ");
  return `${text} ${links}`.replace(/\s+/g, " ").trim();
}

function draftChecksFromLocation() {
  const params = autozsParamsFromLocation();
  const rawChecks = params.get("autozs_checks") || "";
  if (rawChecks) {
    try {
      const parsed = JSON.parse(rawChecks);
      if (Array.isArray(parsed)) {
        return parsed
          .map((item) => ({
            jobId: String(item.job_id || item.jobId || "").trim(),
            draftId: String(item.draft_id || item.draftId || "").trim(),
            title: String(item.title || "").trim(),
          }))
          .filter((item) => item.jobId && item.draftId);
      }
    } catch {}
  }
  const jobIds = (params.get("autozs_job_ids") || "").split(",").map((value) => value.trim()).filter(Boolean);
  const draftIds = (params.get("autozs_draft_ids") || "").split(",").map((value) => value.trim()).filter(Boolean);
  return jobIds.map((jobId, index) => ({ jobId, draftId: draftIds[index] || "", title: "" })).filter((item) => item.jobId && item.draftId);
}

function detectEbayDraftListPresence(check) {
  const haystack = ebayDraftListHaystack();
  const normalized = haystack.toLowerCase();
  const normalizedTitle = normalizeDraftTitle(check.title);
  const normalizedHaystack = normalizeDraftTitle(haystack);
  const draftListReady =
    /seller hub|manage drafts|resume drafts|delete drafts|results\s*:/i.test(haystack) ||
    /looks like you (?:do not|don't) have any drafts|no drafts/i.test(haystack);
  const emptyDrafts =
    /results\s*:\s*0\b/i.test(haystack) ||
    /looks like you (?:do not|don't) have any drafts|you do not have any drafts|no drafts/i.test(haystack);
  if (normalized.includes("sign in")) {
    return { exists: null, message: "eBay sign-in is required before draft verification." };
  }
  if (!draftListReady) {
    return { exists: null, message: "Waiting for eBay Seller Hub Drafts to load." };
  }
  if (emptyDrafts) {
    return { exists: false, message: "eBay Seller Hub Drafts shows zero saved drafts." };
  }
  if (check.draftId && haystack.includes(check.draftId)) {
    return { exists: true, message: `Verified eBay draft ${check.draftId} in Seller Hub Drafts.` };
  }
  if (normalizedTitle && normalizedTitle.length >= 20 && normalizedHaystack.includes(normalizedTitle.slice(0, 60))) {
    return { exists: true, message: `Verified eBay draft by title in Seller Hub Drafts.` };
  }
  return { exists: false, message: `eBay Seller Hub Drafts did not include draft ${check.draftId}.` };
}

async function reportEbayDraftListPresence() {
  const params = autozsParamsFromLocation();
  if (params.get("autozs_verify_drafts") !== "1") return null;
  const checks = draftChecksFromLocation();
  if (!checks.length) return null;
  const results = [];
  for (const check of checks) {
    const presence = detectEbayDraftListPresence(check);
    results.push({ ...check, ...presence });
    if (presence.exists === null) continue;
    const response = await fetch(`${API}/listing-jobs/${encodeURIComponent(check.jobId)}/verify-draft`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        exists: presence.exists,
        ebay_draft_id: check.draftId || null,
        url: location.href,
        message: presence.message,
      }),
    });
    if (!response.ok) throw new Error(await response.text());
  }
  return results;
}

async function reportEbayDraftPresence() {
  const params = autozsParamsFromLocation();
  const jobId = params.get("autozs_job_id");
  if (
    !jobId ||
    (params.get("autozs_verify_draft") !== "1" && params.get("autozs_reconcile_listing") !== "1")
  ) return null;
  const presence = detectEbayDraftPresence();
  if (presence.exists === null) return presence;
  const response = await fetch(`${API}/listing-jobs/${encodeURIComponent(jobId)}/verify-draft`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      exists: presence.exists,
      ebay_draft_id: presence.draftId || null,
      url: location.href,
      message: presence.message,
    }),
  });
  if (!response.ok) throw new Error(await response.text());
  return response.json();
}

function startEbayDraftPresenceReporter() {
  if (!isEbayPage() || window.__autozsEbayDraftPresenceReporterStarted) return;
  const params = autozsParamsFromLocation();
  const singleDraftCheck =
    (params.get("autozs_verify_draft") === "1" || params.get("autozs_reconcile_listing") === "1") &&
    params.get("autozs_job_id");
  const draftListCheck = params.get("autozs_verify_drafts") === "1" && draftChecksFromLocation().length;
  if (!singleDraftCheck && !draftListCheck) return;
  window.__autozsEbayDraftPresenceReporterStarted = true;
  const report = () => (draftListCheck ? reportEbayDraftListPresence() : reportEbayDraftPresence()).catch(() => {});
  [1500, 5000, 10000].forEach((delay) => setTimeout(report, delay));
  window.addEventListener("pageshow", () => setTimeout(report, 750));
}

if (typeof window !== "undefined" && typeof document !== "undefined" && typeof setTimeout !== "undefined") {
  startEbayBrowserAccountReporter();
  startEbayDraftPresenceReporter();
}

function captureSourceProductFromPage() {
  const clean = (value) => String(value || "").replace(/\s+/g, " ").trim();
  const uniq = (values) => [...new Set(values.filter(Boolean).map(clean).filter(Boolean))];
  const normalized = (value) => clean(value).toLowerCase().replace(/[^a-z0-9]/g, "");
  const cleanSourceUrl = () => {
    try {
      const url = new URL(location.href);
      const homeDepotProduct = /(^|\.)homedepot\.com$/i.test(url.hostname) && /^\/p\//i.test(url.pathname);
      const lowesProduct = /(^|\.)lowes\.com$/i.test(url.hostname) && /^\/pd\//i.test(url.pathname);
      if (homeDepotProduct || lowesProduct) {
        url.hostname = homeDepotProduct ? "www.homedepot.com" : "www.lowes.com";
        url.search = "";
        url.hash = "";
        return url.href;
      }
      ["ea_auto_import", "auto_download_test", "autozs_refresh_job", "autozs_refresh_batch", "autozs_error_retry", "autozs_worker_opened_at"].forEach((param) =>
        url.searchParams.delete(param)
      );
      url.hash = "";
      return url.href;
    } catch {
      return location.href;
    }
  };
  const visibleText = document.body.innerText || "";
  if (/(^|\.)lowes\.com$/i.test(location.hostname || "")) {
    throw new Error("Lowe's supplier support is scaffolded, but automated capture is not enabled yet.");
  }
  const homeDepotOops = /oops!!?\s+something\s+went\s+wrong/i.test(visibleText);
  const homeDepotRecoveryPrompt = /please\s+refresh\s+page|need\s+help\?\s+visit\s+our\s+customer\s+service\s+center/i.test(visibleText);
  if (
    location.hostname.includes("homedepot.com") &&
    homeDepotOops &&
    homeDepotRecoveryPrompt
  ) {
    throw new Error("Home Depot showed an error page; refresh this source page and try again.");
  }
  const jsonProducts = [];
  const pathParts = location.pathname.split("/").filter(Boolean);
  const productSlug = pathParts[1] || "";
  const subscriptionPattern = /subscribe|subscription|autoship|auto\s*ship|save\s*&?\s*subscribe|subscribe\s*&?\s*save|get\s+5%\s+off|5%\s+off|subscription\s+price/i;

  document.querySelectorAll('script[type="application/ld+json"]').forEach((script) => {
    try {
      const parsed = JSON.parse(script.textContent);
      const queue = Array.isArray(parsed) ? [...parsed] : [parsed];
      while (queue.length) {
        const item = queue.shift();
        if (!item || typeof item !== "object") continue;
        const type = item["@type"];
        if (type === "Product" || (Array.isArray(type) && type.includes("Product"))) jsonProducts.push(item);
        Object.values(item).forEach((value) => {
          if (value && typeof value === "object") Array.isArray(value) ? queue.push(...value) : queue.push(value);
        });
      }
    } catch {}
  });

  const pageHeading = clean(
    document.querySelector("h1")?.innerText ||
    document.querySelector('meta[property="og:title"]')?.content ||
    ""
  );
  const normalizedHeading = normalized(pageHeading);
  const matchingProductJson = normalizedHeading
    ? jsonProducts.find((item) => {
        const productName = normalized(item?.name);
        return productName && (
          productName === normalizedHeading ||
          productName.includes(normalizedHeading) ||
          normalizedHeading.includes(productName)
        );
      })
    : null;
  const productJson = matchingProductJson || (!normalizedHeading && jsonProducts.length === 1 ? jsonProducts[0] : {});
  const productCodes = uniq([
    productJson.model,
    productJson.mpn,
    productJson.sku,
    productSlug.match(/((?:[a-z]*\d+[a-z]*-){1,4}[a-z]*\d+[a-z]*)$/i)?.[1],
  ])
    .map(normalized)
    .filter((code) => code.length >= 5);
  const offer = Array.isArray(productJson.offers) ? productJson.offers[0] : productJson.offers || {};
  const parsePrice = (value) => {
    const text = clean(value);
    if (!text) return null;
    const explicit =
      text.match(/\$\s*([0-9]{1,4}(?:,[0-9]{3})*)(?:\s*[.]\s*|\s+\.?\s*)([0-9]{2})\b/) ||
      text.match(/\$\s*([0-9]{1,4}(?:,[0-9]{3})*)(?:\.([0-9]{2}))?/);
    if (!explicit) return null;
    const parsed = Number(explicit[1].replace(/,/g, "") + "." + (explicit[2] || "00"));
    return parsed > 0 && parsed < 10000 ? parsed : null;
  };
  const parseStructuredPrice = (value) => {
    const explicit = parsePrice(value);
    if (explicit !== null) return explicit;
    const text = clean(value).replace(/,/g, "");
    if (!/^\d{1,4}(?:\.\d{1,2})?$/.test(text)) return null;
    const parsed = Number(text);
    return parsed > 0 && parsed < 10000 ? parsed : null;
  };

  const detectSubscriptionDiscount = () => {
    const match =
      visibleText.match(/subscribe[\s\S]{0,80}?([0-9]{1,2}(?:\.[0-9]+)?)\s*%\s*off/i) ||
      visibleText.match(/([0-9]{1,2}(?:\.[0-9]+)?)\s*%\s*off[\s\S]{0,80}?subscribe/i);
    if (!match) return null;
    const value = Number(match[1]);
    return value > 0 && value <= 100 ? value : null;
  };

  const detectSubscriptionPrices = () => {
    const prices = [];
    const lines = visibleText.split("\n").map(clean).filter(Boolean);
    lines.forEach((line, index) => {
      const context = lines.slice(Math.max(0, index - 4), index + 5).join(" ");
      if (!subscriptionPattern.test(context)) return;
      const parsed = parsePrice(line);
      if (parsed !== null) prices.push(parsed);
    });
    const broadMatches = visibleText.match(/(?:subscribe|subscription|autoship|auto\s*ship)[\s\S]{0,160}?\$\s*[0-9]{1,4}(?:,[0-9]{3})*(?:\.[0-9]{2})?/gi) || [];
    broadMatches.forEach((match) => {
      const parsed = parsePrice(match);
      if (parsed !== null) prices.push(parsed);
    });
    return uniq(prices.map((price) => price.toFixed(2))).map(Number);
  };

  const detectHomeDepotSalePrice = () => {
    if (!location.hostname.includes("homedepot.com")) return null;
    const lines = visibleText.split("\n").map(clean).filter(Boolean);
    const salePattern = /special\s*buy|special\s*price|sale\s*price|\b(?:sale|savings)\b|new\s*lower\s*price|limited[-\s]*time\s*(?:deal|price)|clearance/i;
    const excludedPattern = /credit\s*card|open(?:ing)?\s+(?:a|new)\s+card|financing|protection\s*plan|delivery|shipping|pickup/i;
    const stripNonActivePrices = (text) =>
      clean(text)
        .replace(/\bwas\s*\$\s*[0-9]{1,4}(?:,[0-9]{3})*(?:\s*[.]\s*|\s+)?[0-9]{0,2}/gi, " ")
        .replace(/\bsave\s*\$\s*[0-9]{1,4}(?:,[0-9]{3})*(?:\s*[.]\s*|\s+)?[0-9]{0,2}(?:\s*\([^)]*\))?/gi, " ")
        .replace(/\bpay\s*\$\s*[0-9]{1,4}(?:,[0-9]{3})*(?:\s*[.]\s*|\s+)?[0-9]{0,2}[\s\S]{0,90}?(?:card|credit|opening|off)/gi, " ");
    const parseSaleContext = (text) => {
      const context = stripNonActivePrices(text);
      if (excludedPattern.test(context.slice(0, Math.max(context.indexOf("$") + 1, 0)))) return null;
      return parsePrice(context);
    };

    const compactSaleMatch = stripNonActivePrices(visibleText)
      .replace(/\bspecial\s+buy\b/gi, "SPECIAL BUY")
      .match(/(?:special\s*buy|special\s*price|sale\s*price|new\s*lower\s*price|limited[-\s]*time\s*(?:deal|price)|clearance)[\s\S]{0,240}?\$\s*[0-9]{1,4}(?:,[0-9]{3})*(?:\s*[.]\s*|\s+)?[0-9]{0,2}/i);
    if (compactSaleMatch) {
      const price = parseSaleContext(compactSaleMatch[0]);
      if (price !== null) return price;
    }

    for (let index = 0; index < lines.length; index += 1) {
      const saleLabel = [lines[index], lines[index + 1]].filter(Boolean).join(" ");
      if (!salePattern.test(saleLabel)) continue;
      const candidates = lines.slice(index, index + 10);
      for (const candidate of candidates) {
        if (excludedPattern.test(candidate) || /^\s*(?:was|save)\b/i.test(candidate)) continue;
        const price = parsePrice(candidate);
        if (price !== null) return price;
      }
      const context = candidates.join(" ");
      const price = parseSaleContext(context);
      if (price !== null && !excludedPattern.test(context.slice(0, Math.max(context.indexOf("$") + 1, 0)))) return price;
    }
    return null;
  };

  const structuredPrices = [];
  const visiblePrices = [];
  const primaryVisiblePrices = [];
  const domPrices = [];
  const nonProductPricePattern =
    /sign\s*up|email|newsletter|credit\s*card|open(?:ing)?\s+(?:a|new)\s+card|financing|protection\s*plan|monthly|per\s+month|\/mo\b|after\s+\$?\d+\s+off|coupon|rebate/i;
  const addDomPrice = (value, context = "") => {
    const text = clean(`${context} ${value}`);
    if (subscriptionPattern.test(text) || nonProductPricePattern.test(text)) return;
    const parsed = parsePrice(value);
    if (parsed !== null) domPrices.push(parsed);
  };
  const structuredOfferPrice = parseStructuredPrice(
    offer.price ?? offer.lowPrice ?? offer.highPrice ?? offer.priceSpecification?.price
  );
  if (structuredOfferPrice !== null) structuredPrices.push(structuredOfferPrice);
  document
    .querySelectorAll('meta[property="product:price:amount"], meta[name="product:price:amount"], meta[itemprop="price"], [itemprop="price"]')
    .forEach((el) => {
      const parsed = parseStructuredPrice(el.content || el.getAttribute("content") || el.getAttribute("value") || el.textContent);
      if (parsed !== null) structuredPrices.push(parsed);
    });
  document
    .querySelectorAll('[data-testid*="price" i], [class*="price" i], [id*="price" i], [aria-label*="price" i], [data-automation-id*="price" i]')
    .forEach((el) => {
      const context = [el.closest("section")?.innerText, el.parentElement?.innerText, el.innerText].filter(Boolean).join(" ");
      addDomPrice(el.innerText || el.textContent || el.getAttribute("aria-label") || el.getAttribute("content") || el.getAttribute("value"), context);
      Object.values(el.dataset || {}).forEach((value) => addDomPrice(value, context));
    });
  const collectVisiblePrices = (lines, destination) => {
    lines.forEach((line, index) => {
      const separateDollarWhole = line.match(/^\$$/);
      const wholeAfterDollar = clean(lines[index + 1] || "").match(/^([0-9]{1,4}(?:,[0-9]{3})*)$/);
      const centsAfterDollar = clean(lines[index + 2] || "").match(/^([0-9]{2})(?:\b|[^0-9])/);
      const dotAfterWhole = clean(lines[index + 2] || "") === ".";
      const centsAfterDot = clean(lines[index + 3] || "").match(/^([0-9]{2})(?:\b|[^0-9])/);
      if (separateDollarWhole && wholeAfterDollar && dotAfterWhole && centsAfterDot) {
        const parsed = Number(`${wholeAfterDollar[1].replace(/,/g, "")}.${centsAfterDot[1]}`);
        if (parsed > 0 && parsed < 10000) destination.push(parsed);
        return;
      }
      if (separateDollarWhole && wholeAfterDollar && centsAfterDollar) {
        const parsed = Number(`${wholeAfterDollar[1].replace(/,/g, "")}.${centsAfterDollar[1]}`);
        if (parsed > 0 && parsed < 10000) destination.push(parsed);
        return;
      }
      const splitPrice = line.match(/^\$\s*([0-9]{1,4}(?:,[0-9]{3})*)$/);
      const nextLineCents = clean(lines[index + 1] || "").match(/^([0-9]{2})(?:\b|[^0-9])/);
      if (splitPrice && nextLineCents) {
        const parsed = Number(`${splitPrice[1].replace(/,/g, "")}.${nextLineCents[1]}`);
        if (parsed > 0 && parsed < 10000) destination.push(parsed);
        return;
      }
      (line.match(/\$\s*[0-9]{1,4}(?:,[0-9]{3})*(?:\s*[.]\s*|\s+)?[0-9]{0,2}/g) || []).forEach((value) => {
        const parsed = parsePrice(value);
        if (parsed !== null) destination.push(parsed);
      });
    });
  };
  const eligibleVisibleLines = visibleText
    .split("\n")
    .map(clean)
    .filter((line) => line && !subscriptionPattern.test(line) && !nonProductPricePattern.test(line));
  collectVisiblePrices(eligibleVisibleLines.slice(0, 80), visiblePrices);
  const productTitleForPrice = normalized(productJson.name || pageHeading);
  const titleLineIndex = productTitleForPrice
    ? eligibleVisibleLines.findIndex((line) => {
        const normalizedLine = normalized(line);
        return normalizedLine && (
          normalizedLine === productTitleForPrice ||
          normalizedLine.includes(productTitleForPrice) ||
          productTitleForPrice.includes(normalizedLine)
        );
      })
    : -1;
  if (titleLineIndex >= 0) {
    const primaryLines = [];
    const recommendationHeading = /customers?\s+also\s+(?:viewed|bought)|frequently\s+bought\s+together|related\s+products|you\s+may\s+also\s+like|recommended\s+for\s+you|loading\s+recommendations/i;
    for (const line of eligibleVisibleLines.slice(titleLineIndex, titleLineIndex + 40)) {
      if (primaryLines.length && recommendationHeading.test(line)) break;
      primaryLines.push(line);
    }
    collectVisiblePrices(primaryLines, primaryVisiblePrices);
  }

  const detectDeliveryAvailability = () => {
    const lines = visibleText.split("\n").map(clean).filter(Boolean);
    if (
      /\bthis product is (?:currently )?unavailable\b|\bout of stock(?:\s+online)?\b|\bnot available in [a-z][a-z .'-]{1,40}\b|\bchange your store or zip code to purchase\b/i.test(visibleText)
    ) return false;
    const unavailablePattern = /\b(?:delivery|shipping)\s+(?:is\s+)?unavailable\b|\bnot available for (?:delivery|shipping)\b|\bcannot be (?:delivered|shipped)\b/i;
    if (unavailablePattern.test(visibleText)) return false;
    const headingIndexes = lines
      .map((line, index) => (/^(?:standard\s+)?delivery$/i.test(line) ? index : -1))
      .filter((index) => index >= 0);
    for (const index of headingIndexes) {
      const context = lines.slice(index, index + 6).join(" ");
      if (/\bunavailable\b|\bnot available\b|\bcannot be delivered\b/i.test(context)) return false;
      if (/\bfree\b|\$\s*\d|\btomorrow\b|\bavailable\b|\bget it by\b/i.test(context)) return true;
    }
    const deliveryElements = [
      document.querySelector('[data-testid="deliveryTile"]'),
      document.querySelector('[aria-label="deliveryTile"]'),
      ...document.querySelectorAll('[data-testid*="delivery" i], [aria-label*="delivery" i]'),
    ].filter(Boolean);
    for (const element of deliveryElements) {
      const text = clean(element.innerText || element.textContent || "");
      if (/\bunavailable\b|\bnot available\b|\bcannot be delivered\b/i.test(text)) return false;
      if (/\bfree\b|\$\s*\d|\btomorrow\b|\bavailable\b|\bget it by\b/i.test(text)) return true;
    }
    return null;
  };
  const deliveryAvailability = detectDeliveryAvailability();

  const detectShipping = () => {
    if (deliveryAvailability === false) return null;
    const lines = visibleText.split("\n").map(clean).filter(Boolean);
    const subscriptionPrices = detectSubscriptionPrices();
    const isSubscriptionPrice = (price) => subscriptionPrices.some((subscriptionPrice) => Math.abs(subscriptionPrice - price) < 0.01);
    const contextAround = (index, radius = 3) => lines.slice(Math.max(0, index - radius), index + radius + 1).join(" ");
    const isSubscriptionContext = (text) => subscriptionPattern.test(text);
    const freeShippingRegex = /free\s+(standard\s+)?(shipping|delivery)|(?:shipping|delivery)\s+(is\s+)?free|ship(?:s|ping)?\s+free/i;
    const shippingThresholdRegex = /\$\s*[0-9]{1,4}(?:\.[0-9]{2})?\s*\+\s*(?:of\s+)?(?:eligible\s+)?(?:items?|orders?|purchase)|(?:items?|orders?|purchase)\s+(?:over|above|of\s+at\s+least)\s+\$\s*[0-9]{1,4}(?:\.[0-9]{2})?|(?:minimum\s+(?:purchase|order)|spend)\s+(?:of\s+)?\$\s*[0-9]{1,4}(?:\.[0-9]{2})?/i;
    const isShippingThresholdContext = (text) => shippingThresholdRegex.test(text);
    const acceleratedDeliveryRegex = /\bget\s+it\s+faster\b|\b(?:within|in)\s+(?:about\s+)?(?:\d+|one|two|three|four|five|six)\s*(?:-|–|—)?\s*hours?\b|\b(?:same[\s-]?day|express|expedited|rush|priority)\s+(?:shipping|delivery)\b|\b(?:shipping|delivery)\s+(?:today|in\s+\d+\s*hours?)\b|\btoday\s+by\s+\d{1,2}(?::\d{2})?\s*(?:am|pm)\b/i;
    const isAcceleratedDeliveryContext = (text) => acceleratedDeliveryRegex.test(text);

    const standardDeliverySection = (() => {
      const headingIndex = lines.findIndex((line) => /^(?:standard\s+)?delivery$/i.test(line));
      if (headingIndex < 0) return "";
      const section = [lines[headingIndex]];
      for (const line of lines.slice(headingIndex + 1, headingIndex + 12)) {
        if (
          /^(?:get\s+it\s+faster|express|expedited|rush|priority|pickup|ship\s+to\s+store)$/i.test(line) ||
          isAcceleratedDeliveryContext(line)
        ) break;
        section.push(line);
      }
      return section.join(" ");
    })();
    if (
      standardDeliverySection &&
      /\bfree\b/i.test(standardDeliverySection) &&
      !isShippingThresholdContext(standardDeliverySection)
    ) return 0;
    if (standardDeliverySection && !isShippingThresholdContext(standardDeliverySection)) {
      const standardPrice = parsePrice(standardDeliverySection);
      if (standardPrice !== null && !isSubscriptionPrice(standardPrice)) return standardPrice;
    }

    // Home Depot's normal fulfillment option is exposed as a stable deliveryTile.
    // Prefer it over optional expedited offers such as "$2.99 today" and never
    // treat order thresholds such as "$25+ of eligible items" as shipping fees.
    const deliveryElements = [
      document.querySelector('[data-testid="deliveryTile"]'),
      document.querySelector('[aria-label="deliveryTile"]'),
      ...document.querySelectorAll('[data-testid*="delivery" i], [aria-label*="delivery" i]'),
    ].filter(Boolean);
    const standardDeliveryTexts = uniq(deliveryElements.map((element) => clean(element.innerText || element.textContent || "")))
      .filter((text) => /\b(?:delivery|shipping)\b/i.test(text))
      .filter((text) => !isAcceleratedDeliveryContext(text))
      .filter((text) => !isShippingThresholdContext(text));
    if (standardDeliveryTexts.some((text) => /\bfree\b/i.test(text))) return 0;
    for (const text of standardDeliveryTexts) {
      const parsed = parsePrice(text);
      if (parsed !== null && !isSubscriptionPrice(parsed)) return parsed;
    }

    const explicitFreeStandardDelivery = lines.some((line, index) => {
      if (!/^(?:standard\s+)?(?:delivery|shipping)$/i.test(line)) return false;
      const context = lines.slice(index, index + 5).join(" ");
      return /\bfree\b/i.test(context) && !isShippingThresholdContext(context);
    });
    if (explicitFreeStandardDelivery) return 0;

    const blocks = [];
    lines.forEach((line, index) => {
      if (/ship|shipping|deliver|delivery|fulfillment/i.test(line)) {
        blocks.push([line, lines[index + 1], lines[index + 2], lines[index + 3]].filter(Boolean).join(" "));
      }
    });
    const relevant = uniq(blocks)
      .filter((line) => !/pickup|installation|truck rental|credit card|returns?|free custom cut|protection plan|assembly/i.test(line))
      .filter((line) => !isSubscriptionContext(line))
      .filter((line) => !isAcceleratedDeliveryContext(line))
      .slice(0, 40);

    for (const line of relevant) {
      if (isShippingThresholdContext(line)) continue;
      const parsed = parsePrice(line);
      if (parsed !== null && !isSubscriptionPrice(parsed)) return parsed;
    }

    const pagePaidMatch = visibleText.match(/(?:delivery|shipping)[\s\S]{0,90}\$\s*[0-9]{1,4}(?:,[0-9]{3})*(?:\.[0-9]{2})?/i);
    const pagePaid = pagePaidMatch ? parsePrice(pagePaidMatch[0]) : null;
    if (
      pagePaid !== null &&
      !isSubscriptionContext(pagePaidMatch[0]) &&
      !isShippingThresholdContext(pagePaidMatch[0]) &&
      !isAcceleratedDeliveryContext(pagePaidMatch[0]) &&
      !isSubscriptionPrice(pagePaid)
    ) return pagePaid;

    const freeRelevant = relevant.some((line) => freeShippingRegex.test(line) && !isShippingThresholdContext(line)) || lines.some((line, index) => {
      const context = contextAround(index, 2);
      return freeShippingRegex.test(context) && !isSubscriptionContext(context) && !isShippingThresholdContext(context);
    });
    return freeRelevant ? 0 : null;
  };

  const imageCandidates = [];
  document.querySelectorAll('meta[property="og:image"], meta[name="og:image"]').forEach((meta) => imageCandidates.push(meta.content));
  const structuredImages = productJson.image ? (Array.isArray(productJson.image) ? productJson.image : [productJson.image]) : [];
  imageCandidates.push(...structuredImages);
  [...document.images].forEach((img) => {
    imageCandidates.push(img.currentSrc, img.src, img.dataset.src, img.dataset.zoom, img.dataset.image, img.dataset.imageUrl);
    imageCandidates.push(...Object.values(img.dataset || {}));
    if (img.srcset) img.srcset.split(",").forEach((part) => imageCandidates.push(part.trim().split(/\s+/)[0]));
  });
  const rawHtml = document.documentElement.innerHTML.replace(/\\u002F/g, "/");
  const htmlImages = rawHtml.match(/https?:\/\/[^"'\\\s<>]+?\.(?:jpg|jpeg|png|webp)(?:\?[^"'\\\s<>]*)?/gi) || [];
  imageCandidates.push(...htmlImages.map((src) => src.replace(/&amp;/g, "&")));
  let images = uniq(
    imageCandidates.map((src) => {
      try {
        return new URL(src, location.href).href;
      } catch {
        return "";
      }
    })
  ).filter((src) => /\.(jpg|jpeg|png|webp)(\?|$)/i.test(src) || src.startsWith("data:image/"));
  if (location.hostname.includes("homedepot.com")) {
    const productImages = images.filter((src) => src.includes("images.thdstatic.com/productImages/"));
    const codeMatches = productCodes.length
      ? productImages.filter((src) => productCodes.some((code) => normalized(decodeURIComponent(src)).includes(code)))
      : [];
    images = dedupeHomeDepotImageVariants(codeMatches.length >= 2 ? codeMatches : productImages.length ? productImages : images)
      .filter((src) => !/contentgrid|heroflattenimage|rackcdn|dropdown|disinfecting-wipes/i.test(src));
  }
  images = images.slice(0, 100);

  const bulletText = [];
  [
    '[data-testid*="bullet"] li',
    '[data-testid*="product-overview"] li',
    '[class*="product-overview"] li',
    '[class*="ProductOverview"] li',
    ".bullet-list li",
    "li",
  ].forEach((selector) =>
    document.querySelectorAll(selector).forEach((el) => {
      const text = clean(el.innerText);
      if (
        text.length >= 12 &&
        text.length <= 220 &&
        !/sponsored|advertisement|sign in|view more details|customer service|check order status|pickup, shipping|pay your credit card|order cancellation|privacy|terms of use/i.test(text)
      ) {
        bulletText.push(text);
      }
    })
  );

  const bullets = uniq(bulletText).slice(0, 12);
  const metaDescription =
    document.querySelector('meta[name="description"]')?.content ||
    document.querySelector('meta[property="og:description"]')?.content ||
    "";

  const homeDepotSalePrice = detectHomeDepotSalePrice();
  const standardPriceText = clean(document.querySelector("#standard-price")?.innerText || "");
  const standardPrice = parsePrice(standardPriceText);
  const salePriceCorroborated = homeDepotSalePrice !== null && [...visiblePrices, ...domPrices, ...structuredPrices]
    .some((candidate) => Math.abs(candidate - homeDepotSalePrice) < 0.01);
  // Home Depot's global savings/promotional copy can place "Get $5 off"
  // close to a sale banner. The sale scanner must never outrank the actual
  // product price unless another product-price source corroborates it.
  const trustedHomeDepotSalePrice = salePriceCorroborated ? homeDepotSalePrice : null;
  const withCentsForSameWhole = (price) => {
    if (price === null || price === undefined || Math.abs(price - Math.round(price)) > 0.001) return price;
    const decimalMatch = [...visiblePrices, ...domPrices, ...structuredPrices].find(
      (candidate) => Math.floor(candidate) === Math.floor(price) && Math.abs(candidate - Math.round(candidate)) > 0.001
    );
    return decimalMatch || price;
  };

  const detectMinimumOrderQuantity = () => {
    const candidates = [];
    const add = (value) => {
      const parsed = Number(value);
      if (Number.isInteger(parsed) && parsed >= 1 && parsed <= 999) candidates.push(parsed);
    };
    const patterns = [
      /minimum\s+(?:order|purchase)\s+quantity\s*(?::|is)?\s*(\d{1,3})\b/i,
      /minimum\s+(?:order|purchase)\s+(?:of\s+)?(\d{1,3})\b/i,
      /(?:must|required\s+to)\s+(?:purchase|buy|order)\s+(?:at\s+least\s+)?(\d{1,3})\b/i,
      /sold\s+in\s+(?:multiples|quantities)\s+of\s+(\d{1,3})\b/i,
    ];
    patterns.forEach((pattern) => {
      const match = visibleText.match(pattern);
      if (match) add(match[1]);
    });
    document
      .querySelectorAll('[data-testid*="minimum-order" i], [class*="minimum-order" i], [id*="minimum-order" i], [aria-label*="minimum order" i]')
      .forEach((el) => {
        const text = clean(el.innerText || el.textContent || el.getAttribute("aria-label"));
        patterns.forEach((pattern) => {
          const match = text.match(pattern);
          if (match) add(match[1]);
        });
        Object.entries(el.dataset || {}).forEach(([key, value]) => {
          if (/min(?:imum)?(?:order|purchase)?quantity/i.test(key)) add(value);
        });
      });
    const queue = [productJson, offer];
    const seen = new Set();
    while (queue.length) {
      const item = queue.shift();
      if (!item || typeof item !== "object" || seen.has(item)) continue;
      seen.add(item);
      Object.entries(item).forEach(([key, value]) => {
        if (/^(?:minimumOrderQuantity|minOrderQuantity|minimumQuantity|minQuantity)$/i.test(key)) add(value?.value ?? value);
        if (value && typeof value === "object") Array.isArray(value) ? queue.push(...value) : queue.push(value);
      });
    }
    return candidates.length ? Math.max(...candidates) : 1;
  };
  const detectHomeDepotPurchasePrice = () => {
    if (!location.hostname.includes("homedepot.com")) return null;
    const purchaseUnit = "(case|carton|box|pallet|package|pack|bundle|roll|piece|each|ea)";
    const explicitPackagePatterns = [
      new RegExp(`\\(\\s*\\$\\s*([0-9]{1,4}(?:,[0-9]{3})*(?:\\.\\d{2})?)\\s*\\/\\s*${purchaseUnit}\\s*\\)`, "i"),
      new RegExp(`\\$\\s*([0-9]{1,4}(?:,[0-9]{3})*(?:\\.\\d{2})?)\\s*(?:per|\\/)\\s*${purchaseUnit}\\b`, "i"),
    ];
    for (const pattern of explicitPackagePatterns) {
      const match = visibleText.match(pattern);
      if (!match) continue;
      const parsed = Number(match[1].replace(/,/g, ""));
      if (parsed > 0 && parsed < 10000) {
        return { price: parsed, basis: "explicit-package-total", unit: String(match[2] || "").toLowerCase() };
      }
    }

    const coverageMatch = visibleText.match(/\bcovers?\s+([0-9]{1,4}(?:\.[0-9]+)?)\s*sq\.?\s*ft\.?/i);
    const rateMatch = visibleText.match(/\$\s*([0-9]{1,4}(?:\.[0-9]{2})?)\s*\/\s*sq\.?\s*ft\.?/i);
    if (coverageMatch && rateMatch) {
      const coverage = Number(coverageMatch[1]);
      const rate = Number(rateMatch[1]);
      const computed = Math.round(coverage * rate * 100) / 100;
      if (computed > 0 && computed < 10000) {
        return { price: computed, basis: "computed-coverage-total", coverage, rate, unit: "coverage" };
      }
    }
    return null;
  };
  const homeDepotPurchasePrice = detectHomeDepotPurchasePrice();
  const bulkPackageUnits = new Set(["case", "carton", "pallet"]);
  const sourceBulkPackage =
    bulkPackageUnits.has(homeDepotPurchasePrice?.unit) ||
    homeDepotPurchasePrice?.basis === "computed-coverage-total";
  const sourceBulkPackageReason = sourceBulkPackage
    ? homeDepotPurchasePrice?.basis === "computed-coverage-total"
      ? `Excluded bulk coverage product (${homeDepotPurchasePrice.coverage} sq. ft. purchase quantity).`
      : `Excluded Home Depot ${homeDepotPurchasePrice.unit} product.`
    : null;
  const sourcePrice = location.hostname.includes("homedepot.com")
    ? homeDepotPurchasePrice?.price || withCentsForSameWhole(trustedHomeDepotSalePrice) || standardPrice || primaryVisiblePrices[0] || structuredOfferPrice || null
    : trustedHomeDepotSalePrice || structuredPrices[0] || visiblePrices[0] || domPrices[0] || null;
  const minimumOrderQuantity = detectMinimumOrderQuantity();

  return {
    source_url: cleanSourceUrl(),
    title: clean(productJson.name || document.querySelector("h1")?.innerText || document.querySelector('meta[property="og:title"]')?.content || document.title),
    source_price: sourcePrice,
    source_purchase_unit: homeDepotPurchasePrice?.unit || null,
    source_bulk_package: sourceBulkPackage,
    source_bulk_package_reason: sourceBulkPackageReason,
    minimum_order_quantity: minimumOrderQuantity,
    detected_shipping: detectShipping(),
    source_in_stock: deliveryAvailability,
    subscription_discount_percent: detectSubscriptionDiscount(),
    description: bullets.length ? bullets.join("\n") : clean(productJson.description || metaDescription),
    image_urls: images.join("\n"),
    capture_build: CAPTURE_BUILD,
    capture_debug: {
      standard_price_text: standardPriceText,
      primary_visible_prices: primaryVisiblePrices.slice(0, 6),
      visible_prices: visiblePrices.slice(0, 6),
      dom_prices: domPrices.slice(0, 6),
      structured_prices: structuredPrices.slice(0, 6),
      detected_sale_price: homeDepotSalePrice,
      sale_price_corroborated: salePriceCorroborated,
      selected_price: sourcePrice,
      purchase_price_basis: homeDepotPurchasePrice?.basis || "displayed-product-price",
      purchase_unit: homeDepotPurchasePrice?.unit || null,
      bulk_package_blocked: sourceBulkPackage,
      displayed_unit_price: homeDepotPurchasePrice?.rate || null,
      purchase_coverage: homeDepotPurchasePrice?.coverage || null,
      minimum_order_quantity: minimumOrderQuantity,
    },
  };
}

function dedupeHomeDepotImageVariants(urls) {
  const variants = new Map();
  urls.forEach((src, index) => {
    let url;
    try {
      url = new URL(src, location.href);
    } catch {
      return;
    }
    const resolutionMatch = url.pathname.match(/_(\d+)(?=\.[a-z0-9]+$)/i);
    const resolution = resolutionMatch ? Number(resolutionMatch[1]) : 0;
    const key = `${url.origin}${url.pathname.replace(/_\d+(?=\.[a-z0-9]+$)/i, "")}`;
    const existing = variants.get(key);
    if (!existing || resolution > existing.resolution) variants.set(key, { src: url.href, resolution, index });
  });
  return [...variants.values()].sort((left, right) => left.index - right.index).map((item) => item.src);
}

async function importCapturedProduct(payload) {
  const response = await fetch(`${API}/products/import-captured`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!response.ok) throw new Error(await response.text());
  return response.json();
}

async function downloadProductImages(productId) {
  const response = await fetch(`${API}/products/${productId}/download-images`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
  });
  if (!response.ok) throw new Error(await response.text());
  const downloadResult = await response.json();
  try {
    const prepResult = await prepareProductImages(productId);
    return {
      ...downloadResult,
      prepare_attempted: prepResult.attempted,
      prepared: prepResult.prepared,
      prep_size: prepResult.size,
    };
  } catch (error) {
    return { ...downloadResult, prepare_error: error.message };
  }
}

async function prepareProductImages(productId, size = 1000) {
  const response = await fetch(`${API}/products/${productId}/prepare-images?size=${encodeURIComponent(size)}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
  });
  if (!response.ok) throw new Error(await response.text());
  return response.json();
}

function imageDownloadStatus(result) {
  const downloaded = `${result.downloaded}/${result.attempted} images downloaded`;
  if (result.prepared !== undefined) {
    return `${downloaded}; ${result.prepared}/${result.prepare_attempted} eBay-ready ${result.prep_size || 1000}px images prepared`;
  }
  if (result.prepare_error) return `${downloaded}; image prep failed: ${result.prepare_error}`;
  return downloaded;
}

async function fetchEbayListingPackage(productId) {
  const response = await fetch(`${API}/products/${productId}/ebay-package`, { cache: "no-store" });
  if (!response.ok) throw new Error(await response.text());
  return response.json();
}

async function startNextListingJob(accountKey = "manual") {
  const query = accountKey ? `?ebay_account_key=${encodeURIComponent(accountKey)}` : "";
  const response = await fetch(`${API}/listing-jobs/next${query}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
  });
  if (!response.ok) throw new Error(await response.text());
  return response.json();
}

async function updateListingJob(jobId, payload) {
  const response = await fetch(`${API}/listing-jobs/${jobId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!response.ok) throw new Error(await response.text());
  return response.json();
}

async function updateEbayRevisionJob(jobId, payload) {
  const response = await fetch(`${API}/ebay/revision-jobs/${encodeURIComponent(jobId)}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!response.ok) throw new Error(await response.text());
  return response.json();
}

function stripListingHtml(value) {
  const container = document.createElement("div");
  container.innerHTML = String(value || "");
  return (container.innerText || container.textContent || String(value || "")).replace(/\s+\n/g, "\n").trim();
}
