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
    const exact = options.find((element) => optionText(element) === target);
    const partial = target === "other" ? null : options.find((element) => optionText(element).includes(target));
    const choice = exact || partial;
    if (choice) {
      choice.click();
      await wait(150);
      return true;
    }
    // Searchable Depop comboboxes filter their menu from a real input event.
    setControlledValue(input, wanted);
    await wait(250);
    const filteredOptions = [...document.querySelectorAll('[role="option"], [role="menuitem"], li')].filter(visible);
    const filtered = filteredOptions.find((element) => optionText(element) === target)
      || (target === "other" ? null : filteredOptions.find((element) => optionText(element).includes(target)));
    if (filtered) filtered.click();
    return Boolean(filtered);
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
      const match = parsed.pathname.match(/^\/products\/([^/]+)(?:\/manage)?\/?$/i);
      if (!match || ["create", "edit"].includes(match[1].toLowerCase())) return null;
      return { id: match[1], url: `${parsed.origin}/products/${match[1]}/` };
    } catch {
      return null;
    }
  }

  function findPublishedListing(pending) {
    const current = listingIdentity(location.href);
    if (current) return current;

    const color = String(pending.color || "").trim().toLowerCase();
    const price = Number(pending.price || 0).toFixed(2);
    const candidates = [...document.querySelectorAll('a[href*="/products/"]')]
      .map((anchor) => {
        const identity = listingIdentity(anchor.href);
        const text = String(anchor.innerText || anchor.closest("article,li,div")?.innerText || "")
          .replace(/\s+/g, " ").trim().toLowerCase();
        let score = 0;
        if (identity && color && text.includes(color)) score += 2;
        if (identity && price !== "0.00" && text.includes(price)) score += 1;
        return { identity, score };
      })
      .filter((candidate) => candidate.identity);
    candidates.sort((a, b) => b.score - a.score);
    return candidates[0]?.score >= 2 ? candidates[0].identity : null;
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
    showStatus("AutoZS confirmed this Depop listing as published.");
  }

  async function watchForPublishedDestination(pending, timeoutMs = 30000) {
    if (!pending?.postClickedAt) return false;
    const deadline = Date.now() + timeoutMs;
    while (Date.now() < deadline) {
      const identity = findPublishedListing(pending);
      if (identity) {
        await confirmPublication(pending, identity);
        return true;
      }
      await wait(500);
    }
    return false;
  }

  async function armPublicationConfirmation(pkg) {
    const pending = {
      jobId: String(jobId),
      variantId: pkg.variant_id,
      title: pkg.title || "",
      color: pkg.color || "",
      price: pkg.price,
      postClickedAt: null,
    };
    await storageSet(PENDING_PUBLICATION_KEY, pending);
    const markPostClicked = async (event) => {
      const button = event.target?.closest?.('button[type="submit"], input[type="submit"]');
      const label = String(button?.innerText || button?.value || "").trim().toLowerCase();
      if (!button || label !== "post") return;
      pending.postClickedAt = new Date().toISOString();
      await storageSet(PENDING_PUBLICATION_KEY, pending);
      watchForPublishedDestination(pending).catch(() => {});
    };
    document.addEventListener("pointerdown", markPostClicked, true);
    document.addEventListener("click", markPostClicked, true);
  }

  async function resumePublicationConfirmation() {
    const pending = await storageGet(PENDING_PUBLICATION_KEY);
    if (pending?.postClickedAt) await watchForPublishedDestination(pending, 15000);
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
    await armPublicationConfirmation(pkg);
    if (!(await waitForElement("upload-input__input"))) {
      throw new Error("Depop listing form did not finish loading");
    }

    // Uploading photos makes Depop rerender the form. Do that first so it
    // cannot erase controlled values written below.
    const imagePaths = [...new Set((pkg.local_image_paths?.length ? pkg.local_image_paths : pkg.image_urls) || [])];
    const uploaded = await uploadImages(imagePaths);
    await wait(1000);

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
    results.push(await selectCombobox("shippingMethods", pkg.shipping_method || "Medium Under 1lb"));
    await wait(300);
    const requiredValuesPersisted = Boolean(
      document.getElementById("description")?.value?.trim()
      && Number(document.getElementById("priceAmount__input")?.value) === Number(pkg.price)
      && document.getElementById("group-input")?.value?.trim()
      && document.getElementById("brand-input")?.value?.trim()
      && document.getElementById("condition-input")?.value?.trim()
    );
    const unresolved = results.filter((result) => !result).length + (requiredValuesPersisted ? 0 : 1);
    const note = unresolved
      ? `Draft filled with ${uploaded} photo(s); ${unresolved} dropdown(s) need review.`
      : `Draft filled with ${uploaded} photo(s), listing details, and shipping. Review it, then post.`;
    await patchJob("needs_review", 90, note);
    showStatus(note);
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
