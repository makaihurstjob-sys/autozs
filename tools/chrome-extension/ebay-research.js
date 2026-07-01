(function () {
  if (window.__autozsEbayResearchTools) return;
  window.__autozsEbayResearchTools = true;

  const SAVE_CLASS = "autozs-save-seller-chip";
  const TOOLBAR_ID = "autozs-research-toolbar";
  const ORIGINAL_ORDER = "autozsOriginalOrder";
  const savedSellerNames = new Set();
  let savedSellersLoaded = false;

  function normalizeSellerUsername(value) {
    const cleaned = String(value || "")
      .replace(/\([^)]*\)/g, " ")
      .replace(/\s+/g, " ")
      .trim()
      .replace(/^@+/, "")
      .replace(/[,:;!]+$/g, "");
    if (/^(seller|contact|message|save seller|see all|shop|feedback)$/i.test(cleaned)) return "";
    return /^[A-Za-z0-9._&-]{2,128}$/.test(cleaned) ? cleaned : "";
  }

  function sellerFromHref(href) {
    const text = String(href || "");
    const usr = text.match(/\/usr\/([^/?#]+)/i);
    if (usr) return decodeURIComponent(usr[1]);
    const feedback = text.match(/feedback_profile\/([^/?#]+)/i);
    if (feedback) return decodeURIComponent(feedback[1]);
    const str = text.match(/\/str\/([^/?#]+)/i);
    if (str) return decodeURIComponent(str[1]);
    return "";
  }

  function sellerFromElement(element) {
    if (!element) return "";
    const hrefSeller = sellerFromHref(element.getAttribute?.("href"));
    if (hrefSeller) return normalizeSellerUsername(hrefSeller);
    const labelSeller = normalizeSellerUsername(element.getAttribute?.("aria-label") || element.getAttribute?.("title"));
    if (labelSeller) return labelSeller;
    return normalizeSellerUsername(element.textContent);
  }

  function isSellerHubPage() {
    return /^\/sh\//i.test(location.pathname || "");
  }

  function sellerHubSellerAnchor(anchor) {
    const username = normalizeSellerUsername(sellerFromHref(anchor.getAttribute?.("href")));
    if (!username) return false;
    const text = String(anchor.textContent || "").trim();
    if (!text) return false;
    if (/^(overview|orders|listings|marketing|advertising|store|performance|payments|research|reports|more|active|inactive|drafts|scheduled)$/i.test(text)) {
      return false;
    }
    const href = String(anchor.getAttribute?.("href") || "");
    return /\/usr\/|feedback_profile/i.test(href);
  }

  function parseSoldCount(text) {
    const value = String(text || "");
    const sold = value.match(/(\d[\d,]*)\s+(?:sold|items sold)/i);
    if (!sold) return 0;
    return Number(sold[1].replace(/,/g, "")) || 0;
  }

  function parseRecentSignal(text) {
    const value = String(text || "");
    const recent = value.match(/(\d[\d,]*)\s+(?:watchers?|viewed|sold)\s+(?:in|within|last|today|this)/i);
    if (!recent) return 0;
    return Number(recent[1].replace(/,/g, "")) || 0;
  }

  function scoreListingText(text) {
    const value = String(text || "");
    return parseSoldCount(value) * 1000 + parseRecentSignal(value);
  }

  function isSellerFeedbackText(value) {
    return /(?:\d+(?:\.\d+)?%\s+positive|\([\d,]+\)\s*$)/i.test(String(value || "").trim());
  }

  function searchResultSellerUsername(nameText, feedbackText) {
    if (!isSellerFeedbackText(feedbackText)) return "";
    return normalizeSellerUsername(nameText);
  }

  function ebayLogoUrl() {
    try {
      return typeof chrome !== "undefined" && chrome.runtime?.getURL ? chrome.runtime.getURL("assets/autozs-logo.png") : "";
    } catch {
      return "";
    }
  }

  function ensureStyles() {
    if (document.getElementById("autozs-research-style")) return;
    const style = document.createElement("style");
    style.id = "autozs-research-style";
    style.textContent = `
      .${SAVE_CLASS} {
        align-items: stretch;
        display: inline-flex;
        height: 27px;
        margin-left: 7px;
        overflow: hidden;
        vertical-align: middle;
      }
      .${SAVE_CLASS} button {
        align-items: center;
        background: #6bb9a9;
        border: 0;
        border-radius: 6px 0 0 6px;
        color: #ffffff;
        cursor: pointer;
        display: inline-flex;
        font: 800 13px/1 Arial, Helvetica, sans-serif;
        justify-content: center;
        min-width: 28px;
        padding: 0 7px;
      }
      .${SAVE_CLASS} button svg {
        display: block;
        height: 16px;
        pointer-events: none;
        width: 16px;
      }
      .${SAVE_CLASS}[data-state="saved"] button { background: #20a05a; }
      .${SAVE_CLASS}[data-state="error"] button { background: #b4422f; }
      .${SAVE_CLASS} img {
        background: #000;
        border-radius: 0 6px 6px 0;
        display: block;
        height: 27px;
        object-fit: cover;
        padding: 2px;
        pointer-events: none;
        width: 34px;
      }
      #${TOOLBAR_ID} {
        align-items: center;
        background: #101a16;
        border: 1px solid rgba(85, 183, 167, .45);
        border-radius: 10px;
        box-shadow: 0 10px 30px rgba(0, 0, 0, .14);
        color: #f2fbf8;
        display: flex;
        gap: 8px;
        margin: 12px 0;
        max-width: max-content;
        padding: 8px;
        position: relative;
        z-index: 2147483640;
      }
      #${TOOLBAR_ID} button {
        background: #55b7a7;
        border: 0;
        border-radius: 7px;
        color: #fff;
        cursor: pointer;
        font: 800 13px/1 Arial, Helvetica, sans-serif;
        padding: 9px 12px;
      }
      #${TOOLBAR_ID} button.secondary { background: #263a33; }
      #${TOOLBAR_ID} span { color: #b9c8c1; font: 700 12px/1.3 Arial, Helvetica, sans-serif; }
      @media (prefers-color-scheme: light) {
        #${TOOLBAR_ID} {
          background: #f7fbf9;
          border-color: #d9e6e1;
          color: #17231f;
        }
        #${TOOLBAR_ID} span { color: #5e6b65; }
        #${TOOLBAR_ID} button.secondary { background: #20352e; }
      }
    `;
    document.documentElement.appendChild(style);
  }

  function sellerIcon(saved = false) {
    if (saved) {
      return '<svg viewBox="0 0 20 20" aria-hidden="true"><path d="M4 10.5 8 14l8-9" fill="none" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round" stroke-width="2.7"/></svg>';
    }
    return '<svg viewBox="0 0 20 20" aria-hidden="true"><path d="M4 3h10l3 3v11H4zM7 3v5h7V3M7 13h7" fill="none" stroke="currentColor" stroke-linejoin="round" stroke-width="2"/></svg>';
  }

  function markSellerSaved(username) {
    const key = String(username || "").toLowerCase();
    if (!key) return;
    savedSellerNames.add(key);
    document.querySelectorAll(`.${SAVE_CLASS}`).forEach((chip) => {
      if (String(chip.dataset.seller || "").toLowerCase() !== key) return;
      chip.dataset.state = "saved";
      const button = chip.querySelector("button");
      if (button) {
        button.innerHTML = sellerIcon(true);
        button.title = `Saved ${chip.dataset.seller} to AutoZS`;
        button.setAttribute("aria-label", button.title);
      }
    });
  }

  async function loadSavedSellers() {
    if (savedSellersLoaded) return;
    savedSellersLoaded = true;
    try {
      const response = await fetch(`${API}/research/sellers`);
      if (!response.ok) return;
      const sellers = await response.json();
      sellers.forEach((seller) => markSellerSaved(seller.username));
    } catch (_) {
      // Research controls remain usable while the local app is offline.
    }
  }

  async function saveSeller(username, chip) {
    if (!username) return;
    chip.dataset.state = "saving";
    const button = chip.querySelector("button");
    if (button) button.textContent = "...";
    try {
      await checkLocalApi();
      const response = await fetch(`${API}/research/sellers`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username, seed_listing_url: location.href }),
      });
      if (!response.ok) throw new Error(await response.text());
      markSellerSaved(username);
    } catch (error) {
      chip.dataset.state = "error";
      if (button) {
        button.textContent = "!";
        button.title = `AutoZS seller save failed: ${error.message || error}`;
      }
    }
  }

  function addSellerChip(target, usernameOverride = "") {
    if (!target || target.dataset.autozsSellerChipAttached === "1") return;
    const username = normalizeSellerUsername(usernameOverride) || sellerFromElement(target);
    if (!username) return;
    target.dataset.autozsSellerChipAttached = "1";

    const chip = document.createElement("span");
    chip.className = SAVE_CLASS;
    chip.dataset.seller = username;
    chip.dataset.state = "idle";

    const save = document.createElement("button");
    save.type = "button";
    save.innerHTML = sellerIcon(false);
    save.title = `Save ${username} to AutoZS`;
    save.setAttribute("aria-label", save.title);
    save.addEventListener("click", (event) => {
      event.preventDefault();
      event.stopPropagation();
      saveSeller(username, chip);
    });

    const logoUrl = ebayLogoUrl();
    if (logoUrl) {
      const logo = document.createElement("img");
      logo.alt = "AutoZS";
      logo.src = logoUrl;
      logo.draggable = false;
      chip.append(save, logo);
    } else {
      chip.append(save);
    }
    target.insertAdjacentElement("afterend", chip);
    if (savedSellerNames.has(username.toLowerCase())) markSellerSaved(username);
  }

  function removeMisplacedSellerHubChips() {
    if (!isSellerHubPage()) return;
    document.querySelectorAll(`.${SAVE_CLASS}`).forEach((chip) => {
      const target = chip.previousElementSibling;
      if (target?.matches?.("a[href]") && sellerHubSellerAnchor(target)) return;
      if (target?.dataset) target.dataset.autozsSellerChipAttached = "";
      chip.remove();
    });
  }

  function findSellerAnchors() {
    const sellerHub = isSellerHubPage();
    const selectors = sellerHub
      ? [
          "a[href*='/usr/']",
          "a[href*='feedback_profile']",
        ]
      : [
          "a[href*='/usr/']",
          "a[href*='/str/']",
          "a[href*='feedback_profile']",
          "[data-testid*='seller' i] a[href]",
          "[class*='seller' i] a[href]",
        ];
    return Array.from(document.querySelectorAll(selectors.join(","))).filter((anchor) => {
      if (anchor.getAttribute("aria-hidden") === "true") return false;
      if (!String(anchor.textContent || "").trim()) return false;
      if (sellerHub) return sellerHubSellerAnchor(anchor);
      return sellerFromElement(anchor);
    });
  }

  function findSearchSellerTargets() {
    const targets = [];
    document.querySelectorAll(".su-card-container__attributes__secondary .s-card__attribute-row").forEach((row) => {
      const children = Array.from(row.children || []);
      if (children.length < 2) return;
      const username = searchResultSellerUsername(children[0].textContent, children[1].textContent);
      if (username) targets.push({ target: children[0], username });
    });
    return targets;
  }

  function commonListingParent(cards) {
    const counts = new Map();
    cards.forEach((card) => {
      if (card.parentElement) counts.set(card.parentElement, (counts.get(card.parentElement) || 0) + 1);
    });
    return Array.from(counts.entries()).sort((left, right) => right[1] - left[1])[0]?.[0] || null;
  }

  function listingCards() {
    const candidates = Array.from(document.querySelectorAll("li.s-item, .s-item, [data-testid='item-card'], article, li"));
    const cards = candidates.filter((element) => {
      if (element.id === TOOLBAR_ID || element.closest(`#${TOOLBAR_ID}`)) return false;
      const text = String(element.innerText || "");
      return element.querySelector("a[href*='/itm/']") && text.length > 40;
    });
    return Array.from(new Set(cards));
  }

  function preserveOriginalOrder(cards) {
    cards.forEach((card, index) => {
      if (!card.dataset[ORIGINAL_ORDER]) card.dataset[ORIGINAL_ORDER] = String(index + 1);
    });
  }

  function sortVisibleListings(status) {
    const cards = listingCards();
    preserveOriginalOrder(cards);
    const parent = commonListingParent(cards);
    if (!parent || cards.length < 2) {
      status.textContent = "No sortable listing cards found";
      return;
    }
    cards
      .map((card) => ({ card, score: scoreListingText(card.innerText || "") }))
      .sort((left, right) => right.score - left.score)
      .forEach((item) => parent.appendChild(item.card));
    const scored = cards.filter((card) => scoreListingText(card.innerText || "") > 0).length;
    status.textContent = scored ? `Sorted ${cards.length} visible listings` : `No visible sales signals found`;
  }

  function resetVisibleListings(status) {
    const cards = listingCards();
    const parent = commonListingParent(cards);
    if (!parent || cards.length < 2) {
      status.textContent = "No listing cards to reset";
      return;
    }
    cards
      .slice()
      .sort((left, right) => Number(left.dataset[ORIGINAL_ORDER] || 0) - Number(right.dataset[ORIGINAL_ORDER] || 0))
      .forEach((card) => parent.appendChild(card));
    status.textContent = "Reset visible listings";
  }

  function toolbarAnchor() {
    return (
      document.querySelector("[data-testid='x-refine__group'], .srp-controls__control, .srp-controls, #mainContent") ||
      document.querySelector("main") ||
      document.body
    );
  }

  function ensureToolbar() {
    if (!/\/sch\/|\/str\/|\/b\//i.test(location.pathname || "")) return;
    if (document.getElementById(TOOLBAR_ID)) return;
    const host = toolbarAnchor();
    if (!host) return;

    const toolbar = document.createElement("div");
    toolbar.id = TOOLBAR_ID;
    const zFilter = document.createElement("button");
    zFilter.type = "button";
    zFilter.textContent = "Z Filter";
    const reset = document.createElement("button");
    reset.type = "button";
    reset.className = "secondary";
    reset.textContent = "Reset";
    const status = document.createElement("span");
    status.textContent = "Most sold first, visible page only";
    zFilter.addEventListener("click", () => sortVisibleListings(status));
    reset.addEventListener("click", () => resetVisibleListings(status));
    toolbar.append(zFilter, reset, status);
    host.insertAdjacentElement(host === document.body ? "afterbegin" : "beforebegin", toolbar);
  }

  function enhancePage() {
    if (!document.body) return;
    ensureStyles();
    removeMisplacedSellerHubChips();
    findSellerAnchors().forEach(addSellerChip);
    if (!isSellerHubPage()) {
      findSearchSellerTargets().forEach(({ target, username }) => addSellerChip(target, username));
    }
    loadSavedSellers();
    ensureToolbar();
  }

  function start() {
    enhancePage();
    const observer = new MutationObserver(() => enhancePage());
    observer.observe(document.documentElement, { childList: true, subtree: true });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", start, { once: true });
  } else {
    start();
  }

  window.__autozsResearchTest = {
    normalizeSellerUsername,
    parseSoldCount,
    scoreListingText,
    isSellerFeedbackText,
    searchResultSellerUsername,
    sellerFromHref,
  };
})();
