(() => {
  if (globalThis.__AUTOZS_DEPOP_FILL__) return;
  globalThis.__AUTOZS_DEPOP_FILL__ = true;

  const API = "http://127.0.0.1:8000";
  const PENDING_PUBLICATION_KEY = "autozsDepopPendingPublication";
  const params = new URLSearchParams(location.search);
  const jobId = params.get("autozs_job_id");
  const isFillRun = params.get("autozs_fill") === "1" && Boolean(jobId);

  const wait = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
  async function waitForElement(id, timeoutMs = 10000) {
    const deadline = Date.now() + timeoutMs;
    while (Date.now() < deadline) {
      const element = document.getElementById(id);
      if (element) return element;
      await wait(150);
    }
    return null;
  }
  const visible = (element) => {
    const rect = element?.getBoundingClientRect?.();
    return Boolean(element && (!rect || (rect.width > 0 && rect.height > 0)));
  };

  function setControlledValue(element, value) {
    if (!element || value === undefined || value === null || value === "") return false;
    const prototype = element.tagName === "TEXTAREA"
      ? globalThis.HTMLTextAreaElement?.prototype
      : globalThis.HTMLInputElement?.prototype;
    const setter = prototype && Object.getOwnPropertyDescriptor(prototype, "value")?.set;
    if (setter) setter.call(element, String(value));
    else element.value = String(value);
    element.dispatchEvent(new Event("input", { bubbles: true }));
    element.dispatchEvent(new Event("change", { bubbles: true }));
    element.dispatchEvent(new Event("blur", { bubbles: true }));
    return true;
  }

  function optionText(element) {
    return String(element?.innerText || element?.textContent || element?.getAttribute?.("aria-label") || "")
      .replace(/\s+/g, " ").trim().toLowerCase();
  }

  const selectionKey = (value) => String(value || "").trim().toLowerCase().replace(/\s+/g, "");

  async function selectCombobox(idPrefix, wanted) {
    if (!wanted) return true;
    const input = document.getElementById(`${idPrefix}-input`);
    const toggle = document.getElementById(`${idPrefix}-toggle-button`);
    if (!input || !toggle) return false;
    toggle.click();
    await wait(250);
    const target = String(wanted).trim().toLowerCase();
    const options = [...document.querySelectorAll('[role="option"], [role="menuitem"], li, button')]
      .filter(visible)
      .filter((element) => !element.id?.endsWith("toggle-button"));
    const exact = options.find((element) => selectionKey(optionText(element)) === selectionKey(target));
    const partial = null;
    const choice = exact || partial;
    if (choice) {
      choice.click();
      await wait(150);
      return selectionKey(input.value) === selectionKey(target);
    }
    // Searchable Depop comboboxes filter their menu from a real input event.
    setControlledValue(input, wanted);
    await wait(250);
    const filteredOptions = [...document.querySelectorAll('[role="option"], [role="menuitem"], li')].filter(visible);
    const filtered = filteredOptions.find((element) => selectionKey(optionText(element)) === selectionKey(target))
;
    if (filtered) filtered.click();
    await wait(150);
    return Boolean(filtered) && selectionKey(input.value) === selectionKey(target);
  }

  function localPathToUrl(path) {
    if (/^https?:\/\//i.test(path)) return path;
    return `${API}/${String(path || "").replace(/^\/+/, "")}`;
  }

  async function imageFile(path, index) {
    const response = await fetch(localPathToUrl(path), { cache: "no-store" });
    if (!response.ok) throw new Error(`image ${index + 1} returned ${response.status}`);
    const blob = await response.blob();
    const original = String(path).split(/[\\/]/).pop() || `depop-${index + 1}.jpg`;
    return new File([blob], original, { type: blob.type || "image/jpeg" });
  }

  async function uploadImages(paths) {
    const input = document.getElementById("upload-input__input");
    if (!input || !paths.length) return 0;
    const files = await Promise.all(paths.slice(0, 4).map(imageFile));
    const transfer = new DataTransfer();
    files.forEach((file) => transfer.items.add(file));
    input.files = transfer.files;
    input.dispatchEvent(new Event("input", { bubbles: true }));
    input.dispatchEvent(new Event("change", { bubbles: true }));
    return files.length;
  }

  function photosReady(expected) {
    const input = document.getElementById("upload-input__input");
    const region = input?.closest?.('[data-testid="image-upload"], [class*="ImageUpload"], [class*="imageUpload"]');
    if (!region || expected < 1) return false;
    if (region.querySelector('[role="progressbar"], [aria-busy="true"], [role="alert"]')) return false;
    // Local blob previews only prove selection, never completed server upload.
    const sources = new Set([...region.querySelectorAll('img')]
      .filter((img) => img.complete && img.naturalWidth > 0 && /^https:\/\//i.test(img.currentSrc || img.src || ""))
      .map((img) => img.currentSrc || img.src));
    return sources.size === expected;
  }

  async function patchJob(status, progress, message) {
    await apiRequest(`/depop/jobs/${encodeURIComponent(jobId)}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ status, progress, message }),
    });
  }

  async function storageGet(key) {
    if (!globalThis.chrome?.storage?.local) return null;
    return (await chrome.storage.local.get(key))?.[key] || null;
  }

  async function storageSet(key, value) {
    if (globalThis.chrome?.storage?.local) await chrome.storage.local.set({ [key]: value });
  }

  async function storageRemove(key) {
    if (globalThis.chrome?.storage?.local) await chrome.storage.local.remove(key);
  }

  function listingIdentity(url) {
    try {
      const parsed = new URL(url, location.origin);
      if (parsed.origin !== "https://www.depop.com") return null;
      const match = parsed.pathname.match(/^\/products\/([^/]+)(?:\/manage)?\/?$/i);
      if (!match || ["create", "edit"].includes(match[1].toLowerCase())) return null;
      return { id: match[1], url: `${parsed.origin}/products/${match[1]}/` };
    } catch {
      return null;
    }
  }

  function findPublishedListing(pending, resumed = false) {
    // A similarly coloured item in the seller hub is not publication evidence.
    // Only follow the originating tab's immediate create -> product navigation.
    const age = Date.now() - Date.parse(pending.postClickedAt);
    if (!Number.isFinite(age) || age < 0 || age > 120000) return null;
    if (!pending.tabToken || sessionStorage.getItem(PENDING_PUBLICATION_KEY) !== pending.tabToken) return null;
    if (resumed) {
      try {
        const referrer = new URL(document.referrer);
        if (referrer.origin !== location.origin || !/^\/products\/create\/?$/.test(referrer.pathname)) return null;
      } catch { return null; }
    }
    const identity = listingIdentity(location.href);
    const accountLinks = [...document.querySelectorAll('header a[aria-label="Likes"], nav a[aria-label="Likes"]')];
    const expectedAccountPath = `/${pending.username}/likes/`;
    if (!pending.username || !accountLinks.some((link) => {
      try { const url = new URL(link.href); return url.origin === location.origin && `${url.pathname.replace(/\/$/, "")}/` === expectedAccountPath; }
      catch { return false; }
    })) return null;
    // Navigation alone can be a manual visit to an unrelated product.
    const product = document.querySelector?.('[itemtype="https://schema.org/Product"]');
    const name = product?.querySelector('[itemprop="name"]')?.textContent?.trim();
    const priceNode = product?.querySelector('[itemprop="price"]');
    const price = priceNode?.getAttribute('content') || priceNode?.textContent;
    if (!identity || name !== pending.title || Number(price) !== Number(pending.price)) return null;
    return identity;
  }

  async function confirmPublication(pending, identity) {
    await apiRequest(`/depop/jobs/${encodeURIComponent(pending.jobId)}/published`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        depop_listing_id: identity.id,
        listing_url: identity.url,
        published_at: new Date().toISOString(),
      }),
    });
    await storageRemove(PENDING_PUBLICATION_KEY);
    sessionStorage.removeItem(PENDING_PUBLICATION_KEY);
    showStatus("AutoZS confirmed this Depop listing as published.");
  }

  async function watchForPublishedDestination(pending, timeoutMs = 30000, resumed = false) {
    if (!pending?.postClickedAt) return false;
    const deadline = Date.now() + timeoutMs;
    while (Date.now() < deadline) {
      const identity = findPublishedListing(pending, resumed);
      if (identity) {
        await confirmPublication(pending, identity);
        return true;
      }
      await wait(500);
    }
    return false;
  }

  async function armPublicationConfirmation(pkg) {
    if (!globalThis.chrome?.storage?.local || !globalThis.sessionStorage) {
      throw new Error("Publication tracking storage is unavailable");
    }
    const existing = await storageGet(PENDING_PUBLICATION_KEY);
    if (existing && (existing.postClickedAt || String(existing.jobId) !== String(jobId))) {
      throw new Error("Another Depop draft or uncertain publication needs review before filling this job");
    }
    const tabToken = crypto.randomUUID();
    sessionStorage.setItem(PENDING_PUBLICATION_KEY, tabToken);
    const pending = {
      tabToken,
      jobId: String(jobId),
      variantId: pkg.variant_id,
      username: pkg.verified_username,
      title: pkg.title || "",
      color: pkg.color || "",
      price: pkg.price,
      postClickedAt: null,
    };
    await storageSet(PENDING_PUBLICATION_KEY, pending);
    let submitting = false;
    let replay = false;
    let ready = false;
    let expectedPhotos = 0;
    const fieldsStillMatch = () => {
      const description = [pkg.title, pkg.description && pkg.description !== pkg.title ? pkg.description : ""].filter(Boolean).join("\n\n");
      return Number.isFinite(Number(pkg.price)) && Number(pkg.price) > 0
        && document.getElementById("description")?.value === description
        && Number(document.getElementById("priceAmount__input")?.value) === Number(pkg.price)
        && [["group", pkg.category], ["brand", pkg.brand], ["condition", pkg.condition],
          ["colour", pkg.color], ["shippingMethods", pkg.shipping_method]].every(([field, value]) =>
          Boolean(value) && selectionKey(document.getElementById(`${field}-input`)?.value) === selectionKey(value));
    };
    const interceptPost = (event) => {
      const button = event.type === "submit" ? event.submitter
        : event.target?.closest?.('button[type="submit"], input[type="submit"]');
      const label = String(button?.innerText || button?.value || "").trim().toLowerCase();
      if (event.type !== "submit" && (!button || label !== "post")) return;
      if (replay) return;
      event.preventDefault();
      event.stopImmediatePropagation();
      if (submitting) return;
      if (!ready || !fieldsStillMatch() || !photosReady(expectedPhotos) || !button || button.disabled) {
        showStatus("Post blocked: listing fields and completed photo uploads need verification.", true);
        return;
      }
      submitting = true;
      (async () => {
        // Persist locally first; any uncertain API outcome remains blocked.
        pending.postClickedAt = new Date().toISOString();
        await storageSet(PENDING_PUBLICATION_KEY, pending);
        await apiRequest(`/depop/jobs/${encodeURIComponent(jobId)}/begin-submission`, {
          method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ account_key: pkg.account_key }),
        });
        if (!fieldsStillMatch() || !photosReady(expectedPhotos) || !button.isConnected || button.disabled) {
          throw new Error("Form changed after submission was armed; review required");
        }
        replay = true;
        try { button.click(); } finally { replay = false; }
        if (!(await watchForPublishedDestination(pending))) {
          showStatus("Post outcome is unconfirmed. This job is held for review; do not repost.", true);
        }
      })().catch((error) => showStatus(`Post held for review: ${error.message}`, true));
    };
    document.addEventListener("click", interceptPost, true);
    document.addEventListener("submit", interceptPost, true);
    return (fieldsReady, count) => { ready = fieldsReady; expectedPhotos = count; };
  }

  async function resumePublicationConfirmation() {
    const pending = await storageGet(PENDING_PUBLICATION_KEY);
    if (pending?.postClickedAt) {
      const identity = findPublishedListing(pending, true);
      if (identity) await confirmPublication(pending, identity);
    }
  }

  function metricNumber(element) {
    const match = String(element?.textContent || "").replace(/,/g, "").match(/\d+/);
    return match ? Number(match[0]) : 0;
  }

  async function syncActiveListingMetrics() {
    if (!String(location.pathname || "").startsWith("/sellinghub/selling/active")) return;
    const deadline = Date.now() + 15000;
    let rows = [];
    while (Date.now() < deadline) {
      rows = [...document.querySelectorAll('li:has(a[href*="/products/"][href*="/manage/"])')];
      if (rows.length) break;
      await wait(500);
    }
    if (!rows.length) return;
    const variants = await apiRequest("/depop/variants");
    if (!Array.isArray(variants)) return;
    const byListingId = new Map(variants.filter((item) => item.depop_listing_id).map((item) => [item.depop_listing_id, item]));
    for (const row of rows) {
      const link = row.querySelector('a[href*="/products/"][href*="/manage/"]');
      const identity = listingIdentity(link?.href || "");
      const variant = identity && byListingId.get(identity.id);
      const root = row.querySelector('[data-testid="desktopInsights"]') || row.querySelector('[data-testid="mobileInsights"]');
      const insights = [...(root?.firstElementChild?.children || [])];
      if (!variant || insights.length < 5) continue;
      const payload = {
        offers_count: metricNumber(insights[0]),
        bags_count: metricNumber(insights[1]),
        likes_count: metricNumber(insights[2]),
        views_count: metricNumber(insights[3].querySelector('[class*="boostViewsText"]')),
        clicks_count: metricNumber(insights[4].querySelector('[class*="boostViewsText"]')),
        metrics_synced_at: new Date().toISOString(),
      };
      await apiRequest(`/depop/variants/${encodeURIComponent(variant.id)}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
    }
  }

  async function apiRequest(path, options = {}) {
    // Depop pages can leave a direct localhost fetch pending indefinitely.
    // The extension service worker already owns the authenticated AutoZS API
    // proxy, so use it from the live content-script context.
    if (globalThis.chrome?.runtime?.sendMessage) {
      const result = await chrome.runtime.sendMessage({
        type: "autozs-api-proxy",
        path,
        method: options.method || "GET",
        headers: options.headers,
        body: options.body,
      });
      if (!result?.ok) throw new Error(result?.error || `${path} returned ${result?.status || 0}`);
      return result.body ? JSON.parse(result.body) : null;
    }
    const response = await fetch(`${API}${path}`, { ...options, cache: "no-store" });
    if (!response.ok) throw new Error(`${path} returned ${response.status}`);
    return typeof response.json === "function" ? response.json() : null;
  }

  function showStatus(message, error = false) {
    let badge = document.getElementById("autozs-depop-fill-status");
    if (!badge) {
      badge = document.createElement("div");
      badge.id = "autozs-depop-fill-status";
      Object.assign(badge.style, {
        position: "fixed", right: "18px", bottom: "18px", zIndex: "2147483647",
        padding: "12px 15px", maxWidth: "360px", borderRadius: "8px",
        color: "white", font: "600 14px system-ui", boxShadow: "0 8px 30px rgba(0,0,0,.3)",
      });
      document.documentElement.appendChild(badge);
    }
    badge.style.background = error ? "#8f3d2e" : "#166b5f";
    badge.textContent = message;
  }

  async function run() {
    showStatus("AutoZS is loading this Depop draft…");
    const pkg = await apiRequest(`/depop/jobs/${encodeURIComponent(jobId)}`);
    if (pkg.status !== "running" || pkg.depop_listing_id) {
      throw new Error("This job is not an active unpublished Depop draft");
    }
    if (!pkg.account_key || params.get("autozs_account_key") !== pkg.account_key) {
      throw new Error("Depop runner account does not match the assigned job");
    }
    if (!(await waitForElement("upload-input__input"))) {
      throw new Error("Depop listing form did not finish loading");
    }

    const accounts = await apiRequest("/depop/accounts");
    const account = accounts.find((item) => item.key === pkg.account_key);
    const expectedUsername = String(account?.username || "").replace(/^@/, "").toLowerCase();
    const profileLinks = [...document.querySelectorAll('header a[aria-label="Likes"], nav a[aria-label="Likes"]')];
    const observedUsernames = new Set(profileLinks.map((link) => {
      try {
        const url = new URL(link.href, location.origin);
        return url.origin === "https://www.depop.com" ? url.pathname.match(/^\/([^/]+)\/likes\/?$/)?.[1]?.toLowerCase() : null;
      } catch { return null; }
    }).filter(Boolean));
    if (!account?.enabled || !account.writes_enabled || !expectedUsername
      || observedUsernames.size !== 1 || !observedUsernames.has(expectedUsername)) {
      throw new Error("Depop signed-in username does not match the enabled listing account");
    }

    pkg.verified_username = expectedUsername;
    const setPublicationReadiness = await armPublicationConfirmation(pkg);

    // Uploading photos makes Depop rerender the form. Do that first so it
    // cannot erase controlled values written below.
    const imagePaths = [...new Set((pkg.local_image_paths?.length ? pkg.local_image_paths : pkg.image_urls) || [])];
    const uploaded = await uploadImages(imagePaths);
    for (let attempt = 0; uploaded > 0 && attempt < 60 && !photosReady(uploaded); attempt++) {
      await wait(500);
    }

    // Depop has no title input: its listing title is derived from description.
    // Put the curated title first, then the longer copy, without duplicating it.
    const description = [pkg.title, pkg.description && pkg.description !== pkg.title ? pkg.description : ""]
      .filter(Boolean).join("\n\n");
    setControlledValue(document.getElementById("description"), description);
    setControlledValue(document.getElementById("priceAmount__input"), Number(pkg.price).toFixed(2));

    // Depop allows only one listbox open at a time. Running these concurrently
    // makes each toggle close the previous menu before its option is clicked.
    const results = [];
    for (const [field, value] of [
      ["group", pkg.category],
      ["brand", pkg.brand],
      ["condition", pkg.condition],
      ["colour", pkg.color],
    ]) {
      results.push(await selectCombobox(field, value));
    }
    const usps = document.getElementById("usps__shipping");
    if (usps && !usps.checked) usps.click();
    await wait(200);
    results.push(await selectCombobox("shippingMethods", pkg.shipping_method));
    await wait(300);
    const requiredValuesPersisted = Boolean(
      document.getElementById("description")?.value?.trim()
      && Number(document.getElementById("priceAmount__input")?.value) === Number(pkg.price)
      && document.getElementById("group-input")?.value?.trim()
      && document.getElementById("brand-input")?.value?.trim()
      && document.getElementById("condition-input")?.value?.trim()
    );
    const unresolved = (!pkg.shipping_method || !pkg.category || !pkg.brand || !pkg.condition ? 1 : 0) + results.filter((result) => !result).length + (requiredValuesPersisted ? 0 : 1);
    setPublicationReadiness(unresolved === 0, uploaded);
    const photosVerified = photosReady(uploaded);
    const note = !photosVerified
      ? `Draft filled; photo upload completion is unverified. Post is blocked pending review.`
      : unresolved
      ? `Draft filled with ${uploaded} photo(s); ${unresolved} dropdown(s) need review.`
      : `Draft filled with ${uploaded} photo(s), listing details, and shipping. Review it, then post.`;
    if (unresolved || !photosVerified) await patchJob("needs_review", 90, note);
    showStatus(note);
    const scheduler = await storageGet("autozsDepopScheduler");
    if (!unresolved && photosVerified && scheduler?.enabled === true && scheduler?.autoPublish === true
      && scheduler.accountKey === pkg.account_key) {
      const buttons = [...document.querySelectorAll('button[type="submit"], input[type="submit"]')]
        .filter((button) => visible(button) && !button.disabled && optionText(button) === "post");
      if (buttons.length !== 1) throw new Error("A unique enabled Post button was not found");
      // The capturing handler owns durable authorization and the only replay.
      buttons[0].click();
    }
  }

  const task = isFillRun ? run() : Promise.all([resumePublicationConfirmation(), syncActiveListingMetrics()]);
  if (!isFillRun && String(location.pathname || "").startsWith("/sellinghub/selling/active")) {
    setInterval(() => syncActiveListingMetrics().catch(() => {}), 5 * 60 * 1000);
  }
  task.catch(async (error) => {
    const message = `Depop fill stopped: ${error.message}`;
    showStatus(message, true);
    if (isFillRun) {
      try { await patchJob("needs_review", 0, message); } catch {}
    }
  });
})();
