(() => {
  const API_BASE = "https://desktop-56u49jf.tailb2892a.ts.net:8443";
  const PRODUCT_PATH = /^\/p\/.+\/\d{6,}(?:\/)?$/i;
  const FILTERS = [
    ["all", "All"],
    ["top-rated", "Top Rated"],
    ["exclusive", "Exclusive"],
    ["top-rated-exclusive", "Top Rated + Exclusive"],
    ["best-seller", "Best Seller"],
  ];

  function canonicalHomeDepotProductUrl(value, base = "https://www.homedepot.com/") {
    try {
      const url = new URL(String(value || ""), base);
      if (!/(^|\.)homedepot\.com$/i.test(url.hostname) || !PRODUCT_PATH.test(url.pathname)) return "";
      return `https://www.homedepot.com${url.pathname.replace(/\/+$/, "")}`;
    } catch {
      return "";
    }
  }

  function detectProductBadges(value) {
    const text = String(value || "").replace(/\s+/g, " ").trim();
    return {
      topRated: /\btop[\s-]*rated\b/i.test(text),
      exclusive: /\bexclusive\b/i.test(text),
      bestSeller: /\bbest[\s-]*seller\b|\bbestseller\b/i.test(text),
    };
  }

  function badgeLabels(badges) {
    const labels = [];
    if (badges?.topRated) labels.push("Top Rated");
    if (badges?.exclusive) labels.push("Exclusive");
    if (badges?.bestSeller) labels.push("Best Seller");
    return labels;
  }

  function matchesFilter(product, filter) {
    if (filter === "top-rated-exclusive") return product.badges.topRated && product.badges.exclusive;
    if (filter === "top-rated") return product.badges.topRated && !product.badges.exclusive;
    if (filter === "exclusive") return product.badges.exclusive && !product.badges.topRated;
    if (filter === "best-seller") return product.badges.bestSeller;
    return true;
  }

  function productTitle(anchor, card, url) {
    const candidates = [
      anchor?.getAttribute?.("aria-label"),
      anchor?.getAttribute?.("title"),
      anchor?.querySelector?.("img")?.getAttribute?.("alt"),
      card?.querySelector?.('[data-testid*="title" i], [class*="title" i], h2, h3, h4')?.textContent,
    ];
    const found = candidates
      .map((value) => String(value || "").replace(/\s+/g, " ").trim())
      .find((value) => value && !/^(shop|view|product|image)$/i.test(value));
    if (found) return found;
    try {
      const slug = new URL(url).pathname.split("/").filter(Boolean).slice(1, -1).join(" ");
      return decodeURIComponent(slug).replace(/-/g, " ").replace(/\s+/g, " ").trim() || "Home Depot product";
    } catch {
      return "Home Depot product";
    }
  }

  function findBadgeCard(anchor) {
    let node = anchor;
    let fallback = null;
    for (let depth = 0; node && depth < 9; depth += 1, node = node.parentElement) {
      const text = String(node.innerText || node.textContent || "").replace(/\s+/g, " ").trim();
      const badges = detectProductBadges(text);
      if (!badgeLabels(badges).length) continue;
      const productLinks = Array.from(node.querySelectorAll?.('a[href*="/p/"]') || [])
        .map((link) => canonicalHomeDepotProductUrl(link.href || link.getAttribute?.("href")))
        .filter(Boolean);
      const uniqueLinks = new Set(productLinks);
      const candidate = { node, badges };
      if (!fallback) fallback = candidate;
      if (uniqueLinks.size <= 2 && text.length <= 3500) return candidate;
    }
    return fallback;
  }

  function scanSuggestedProducts(root = document, currentUrl = location.href) {
    const current = canonicalHomeDepotProductUrl(currentUrl);
    const products = new Map();
    const anchors = Array.from(root.querySelectorAll?.('a[href*="/p/"]') || []);
    anchors.forEach((anchor) => {
      const url = canonicalHomeDepotProductUrl(anchor.href || anchor.getAttribute?.("href"), currentUrl);
      if (!url || url === current) return;
      const match = findBadgeCard(anchor);
      if (!match || !badgeLabels(match.badges).length) return;
      const existing = products.get(url);
      if (existing) {
        existing.badges.topRated ||= match.badges.topRated;
        existing.badges.exclusive ||= match.badges.exclusive;
        existing.badges.bestSeller ||= match.badges.bestSeller;
        return;
      }
      products.set(url, {
        url,
        title: productTitle(anchor, match.node, url),
        badges: { ...match.badges },
      });
    });
    return Array.from(products.values()).sort((left, right) => left.title.localeCompare(right.title));
  }

  const helpers = {
    badgeLabels,
    canonicalHomeDepotProductUrl,
    detectProductBadges,
    matchesFilter,
    scanSuggestedProducts,
  };
  globalThis.__autozsHomeDepotProductHunt = helpers;

  if (typeof document === "undefined" || !/(^|\.)homedepot\.com$/i.test(location.hostname || "")) return;
  if (/^(?:\/cart|\/checkout|\/myaccount|\/auth)/i.test(location.pathname || "")) return;
  if (new URLSearchParams(location.search).has("ea_auto_import")) return;
  if (new URLSearchParams(location.search).has("autozs_refresh_job")) return;
  if (document.getElementById("autozs-product-hunt-host")) return;

  const host = document.createElement("div");
  host.id = "autozs-product-hunt-host";
  host.style.cssText = "position:fixed;right:20px;bottom:92px;z-index:2147483645;";
  const shadow = host.attachShadow({ mode: "open" });
  shadow.innerHTML = `
    <style>
      :host {
        --az-bg: #111a15;
        --az-panel: #17211c;
        --az-line: #314139;
        --az-ink: #f0f6f2;
        --az-muted: #9eaca4;
        --az-accent: #4bb7a6;
        --az-accent-strong: #6cd2c2;
        color: var(--az-ink);
        font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      }
      * { box-sizing: border-box; }
      button { font: inherit; }
      .launcher {
        align-items: center;
        background: var(--az-bg);
        border: 1px solid var(--az-line);
        border-radius: 999px;
        box-shadow: 0 10px 30px rgba(0,0,0,.28);
        color: var(--az-ink);
        cursor: pointer;
        display: flex;
        font-size: 14px;
        font-weight: 800;
        gap: 8px;
        padding: 11px 16px;
      }
      .launcher-dot { background: var(--az-accent); border-radius: 50%; height: 9px; width: 9px; }
      .panel {
        background: var(--az-bg);
        border: 1px solid var(--az-line);
        border-radius: 14px;
        bottom: 0;
        box-shadow: 0 22px 70px rgba(0,0,0,.42);
        display: none;
        flex-direction: column;
        max-height: min(720px, calc(100vh - 116px));
        overflow: hidden;
        position: absolute;
        right: 0;
        width: min(460px, calc(100vw - 32px));
      }
      .panel.open { display: flex; }
      .header { align-items: flex-start; border-bottom: 1px solid var(--az-line); display: flex; gap: 12px; padding: 18px; }
      .header-copy { flex: 1; min-width: 0; }
      h2 { font-size: 20px; line-height: 1.2; margin: 0 0 5px; }
      .subtitle { color: var(--az-muted); font-size: 12px; line-height: 1.4; }
      .icon-button {
        background: #26332d;
        border: 0;
        border-radius: 8px;
        color: var(--az-ink);
        cursor: pointer;
        font-size: 18px;
        height: 34px;
        width: 34px;
      }
      .filters { display: flex; flex-wrap: wrap; gap: 7px; padding: 13px 18px 8px; }
      .filter {
        background: transparent;
        border: 1px solid var(--az-line);
        border-radius: 999px;
        color: var(--az-muted);
        cursor: pointer;
        font-size: 11px;
        font-weight: 750;
        padding: 7px 10px;
      }
      .filter.active { background: #203c35; border-color: var(--az-accent); color: var(--az-accent-strong); }
      .summary { align-items: center; color: var(--az-muted); display: flex; font-size: 12px; gap: 10px; padding: 5px 18px 11px; }
      .summary strong { color: var(--az-ink); }
      .refresh { background: transparent; border: 0; color: var(--az-accent-strong); cursor: pointer; margin-left: auto; padding: 0; }
      .results { display: grid; gap: 8px; min-height: 130px; overflow: auto; padding: 0 18px 14px; }
      .empty {
        align-content: center;
        border: 1px dashed var(--az-line);
        border-radius: 10px;
        color: var(--az-muted);
        display: grid;
        font-size: 13px;
        line-height: 1.45;
        min-height: 130px;
        padding: 22px;
        text-align: center;
      }
      .product {
        align-items: flex-start;
        background: var(--az-panel);
        border: 1px solid var(--az-line);
        border-radius: 10px;
        display: grid;
        gap: 10px;
        grid-template-columns: auto minmax(0, 1fr);
        padding: 11px;
      }
      .product input { accent-color: var(--az-accent); height: 17px; margin: 2px 0 0; width: 17px; }
      .title { color: var(--az-ink); display: block; font-size: 13px; font-weight: 750; line-height: 1.3; overflow: hidden; text-decoration: none; }
      .title:hover { color: var(--az-accent-strong); text-decoration: underline; }
      .badges { display: flex; flex-wrap: wrap; gap: 5px; margin-top: 7px; }
      .badge { background: #263a31; border-radius: 999px; color: #8de4b4; font-size: 10px; font-weight: 800; padding: 4px 7px; text-transform: uppercase; }
      .actions { border-top: 1px solid var(--az-line); display: grid; gap: 8px; grid-template-columns: 1fr 1.35fr; padding: 14px 18px 18px; }
      .action {
        background: #2a3831;
        border: 0;
        border-radius: 9px;
        color: var(--az-ink);
        cursor: pointer;
        font-size: 13px;
        font-weight: 800;
        min-height: 42px;
        padding: 9px;
      }
      .action.primary { background: var(--az-accent); color: #07130f; }
      .action:disabled { cursor: not-allowed; opacity: .45; }
      .status { color: var(--az-muted); font-size: 11px; grid-column: 1 / -1; line-height: 1.4; min-height: 16px; }
      @media (max-width: 600px) {
        :host { bottom: 70px; right: 10px; }
        .panel { max-height: calc(100vh - 84px); width: calc(100vw - 20px); }
        .launcher { padding: 10px 13px; }
      }
    </style>
    <button class="launcher" type="button"><span class="launcher-dot"></span>Suggested Products</button>
    <section class="panel" aria-label="AutoZS suggested product finder">
      <div class="header">
        <div class="header-copy">
          <h2>Suggested Products</h2>
          <div class="subtitle">Collect qualifying Home Depot recommendations from this page.</div>
        </div>
        <button class="icon-button close" type="button" aria-label="Close">×</button>
      </div>
      <div class="filters">
        ${FILTERS.map(([key, label]) => `<button class="filter${key === "all" ? " active" : ""}" type="button" data-filter="${key}">${label}</button>`).join("")}
      </div>
      <div class="summary"><strong class="count">0 products</strong><span>currently loaded</span><button class="refresh" type="button">Scan again</button></div>
      <div class="results"></div>
      <div class="actions">
        <button class="action copy" type="button" disabled>Copy Links</button>
        <button class="action primary import" type="button" disabled>Import as Drafts</button>
        <div class="status" role="status" aria-live="polite"></div>
      </div>
    </section>
  `;
  (document.documentElement || document.body).appendChild(host);

  const launcher = shadow.querySelector(".launcher");
  const panel = shadow.querySelector(".panel");
  const results = shadow.querySelector(".results");
  const count = shadow.querySelector(".count");
  const copyButton = shadow.querySelector(".copy");
  const importButton = shadow.querySelector(".import");
  const status = shadow.querySelector(".status");
  let products = [];
  let activeFilter = "all";
  let selected = new Set();

  const escapeHtml = (value) =>
    String(value || "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");

  const visibleProducts = () => products.filter((product) => matchesFilter(product, activeFilter));
  const selectedProducts = () => visibleProducts().filter((product) => selected.has(product.url));

  const render = () => {
    const visible = visibleProducts();
    count.textContent = `${visible.length} product${visible.length === 1 ? "" : "s"}`;
    if (!visible.length) {
      results.innerHTML = `<div class="empty">No matching recommendations are loaded yet.<br>Scroll through the product suggestions, then choose <strong>Scan again</strong>.</div>`;
    } else {
      results.innerHTML = visible
        .map((product) => `
          <label class="product">
            <input type="checkbox" data-url="${escapeHtml(product.url)}" ${selected.has(product.url) ? "checked" : ""}>
            <span>
              <a class="title" href="${escapeHtml(product.url)}" target="_blank" rel="noreferrer">${escapeHtml(product.title)}</a>
              <span class="badges">${badgeLabels(product.badges).map((badge) => `<span class="badge">${escapeHtml(badge)}</span>`).join("")}</span>
            </span>
          </label>
        `)
        .join("");
    }
    const selectionCount = selectedProducts().length;
    copyButton.disabled = selectionCount === 0;
    importButton.disabled = selectionCount === 0;
    copyButton.textContent = selectionCount ? `Copy ${selectionCount} Link${selectionCount === 1 ? "" : "s"}` : "Copy Links";
    importButton.textContent = selectionCount ? `Import ${selectionCount} as Draft${selectionCount === 1 ? "" : "s"}` : "Import as Drafts";
  };

  const scan = () => {
    products = scanSuggestedProducts();
    selected = new Set(products.map((product) => product.url));
    status.textContent = products.length
      ? `Found ${products.length} qualifying recommendation${products.length === 1 ? "" : "s"}.`
      : "Nothing found yet. Scroll through the recommendation rows so Home Depot loads their cards.";
    render();
  };

  const copyLinks = async (links) => {
    const value = links.join("\n");
    try {
      await navigator.clipboard.writeText(value);
      return;
    } catch {
      const textarea = document.createElement("textarea");
      textarea.value = value;
      textarea.style.cssText = "position:fixed;opacity:0;pointer-events:none;";
      document.body.appendChild(textarea);
      textarea.select();
      document.execCommand("copy");
      textarea.remove();
    }
  };

  launcher.addEventListener("click", () => {
    panel.classList.add("open");
    launcher.style.display = "none";
    scan();
  });
  shadow.querySelector(".close").addEventListener("click", () => {
    panel.classList.remove("open");
    launcher.style.display = "flex";
  });
  shadow.querySelector(".refresh").addEventListener("click", scan);
  shadow.querySelectorAll(".filter").forEach((button) => {
    button.addEventListener("click", () => {
      activeFilter = button.dataset.filter || "all";
      shadow.querySelectorAll(".filter").forEach((candidate) => candidate.classList.toggle("active", candidate === button));
      render();
    });
  });
  results.addEventListener("change", (event) => {
    const checkbox = event.target?.closest?.('input[type="checkbox"][data-url]');
    if (!checkbox) return;
    if (checkbox.checked) selected.add(checkbox.dataset.url);
    else selected.delete(checkbox.dataset.url);
    render();
  });
  copyButton.addEventListener("click", async () => {
    const chosen = selectedProducts();
    await copyLinks(chosen.map((product) => product.url));
    status.textContent = `Copied ${chosen.length} Home Depot link${chosen.length === 1 ? "" : "s"}.`;
  });
  importButton.addEventListener("click", async () => {
    const chosen = selectedProducts();
    if (!chosen.length) return;
    const requested = chosen.length;
    importButton.disabled = true;
    copyButton.disabled = true;
    importButton.textContent = `Adding 0/${requested} drafts...`;
    status.textContent = `Sending ${requested} selected product${requested === 1 ? "" : "s"} to AutoZS...`;
    try {
      const response = await fetch(`${API_BASE}/products/import`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          urls: chosen.map((product) => product.url).join("\n"),
          supplier_override: "home_depot",
        }),
      });
      if (!response.ok) throw new Error((await response.text()) || `AutoZS returned ${response.status}`);
      const payload = await response.json();
      const imported = Math.min(requested, Number(payload.imported ?? requested));
      const remainder = Math.max(0, requested - imported);
      status.textContent = remainder
        ? `${imported}/${requested} drafts accepted; ${remainder} could not be added. AutoZS is building the accepted drafts now.`
        : `${imported}/${requested} drafts accepted. AutoZS is building them now.`;
      importButton.textContent = `Added ${imported}/${requested}`;
      setTimeout(render, 1600);
    } catch (error) {
      status.textContent = `Import failed: ${error.message || String(error)}`;
      render();
    }
  });
})();
