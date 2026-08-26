(() => {
  if (window.__autozsCustomerMessageRunner) return;
  window.__autozsCustomerMessageRunner = true;

  const messageIdFromLocation = () => {
    const search = new URLSearchParams(location.search).get("autozs_customer_message");
    const hash = new URLSearchParams(String(location.hash || "").replace(/^#/, "")).get("autozs_customer_message");
    return Number(search || hash || 0);
  };
  const isTopFrame = (() => {
    try {
      return !window.top || window.top === window.self;
    } catch {
      return false;
    }
  })();
  const initialMessageId = messageIdFromLocation();
  let activeMessageId = initialMessageId;
  if (isTopFrame && !initialMessageId) return;

  // The Orders page opens the real composer in an eBay-owned iframe. Its
  // URL does not inherit our runner hash and it may move between ebay.com
  // and mesg.ebay.com, so the top frame explicitly hands the queued message
  // ID to every child frame. The content script runs in those frames via
  // manifest all_frames and fills the composer from inside its own document,
  // avoiding cross-origin DOM access entirely.
  let resolveRelayedMessageId = null;
  const relayedMessageId = new Promise((resolve) => { resolveRelayedMessageId = resolve; });
  window.addEventListener("message", (event) => {
    const candidate = Number(event?.data?.autozsCustomerMessageId || 0);
    if (!candidate) return;
    resolveRelayedMessageId?.(candidate);
  });
  const relayMessageIdToFrames = (messageId) => {
    document.querySelectorAll("iframe").forEach((frame) => {
      try {
        frame.contentWindow?.postMessage({ autozsCustomerMessageId: messageId }, "*");
      } catch {}
    });
  };

  const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
  const normalizedText = (value) => String(value || "").replace(/\s+/g, " ").trim().toLowerCase();
  const isVisible = (element) => {
    if (!element || element.disabled) return false;
    const rect = element.getBoundingClientRect?.();
    return Boolean(rect && rect.width > 0 && rect.height > 0);
  };
  const emitInput = (element, value) => {
    if (element.isContentEditable) {
      element.focus();
      element.textContent = value;
    } else {
      const prototype = element.tagName === "TEXTAREA"
        ? HTMLTextAreaElement.prototype
        : HTMLInputElement.prototype;
      const setter = Object.getOwnPropertyDescriptor(prototype, "value")?.set;
      if (setter) setter.call(element, value);
      else element.value = value;
      element.focus();
    }
    element.dispatchEvent(new InputEvent("input", { bubbles: true, inputType: "insertText", data: value }));
    element.dispatchEvent(new Event("change", { bubbles: true }));
  };
  // Same-origin iframes (the Orders-list "Message buyer" panel renders its
  // composer inside one, src starting as the parent page's own URL) can be
  // read directly -- this only adds a second place to look, it never
  // reaches across origins.
  const readableIframeDocuments = () => {
    const docs = [];
    document.querySelectorAll("iframe").forEach((frame) => {
      try {
        if (frame.contentDocument) docs.push(frame.contentDocument);
      } catch {}
    });
    return docs;
  };
  const findComposer = () => {
    const roots = [document, ...readableIframeDocuments()];
    for (const root of roots) {
      const candidates = [
        ...root.querySelectorAll('textarea[name*="message" i], textarea[id*="message" i], textarea'),
        ...root.querySelectorAll('[contenteditable="true"][role="textbox"], [contenteditable="true"]'),
      ];
      const found = candidates.find(isVisible);
      if (found) return found;
    }
    return null;
  };
  const findSubject = () => {
    const roots = [document, ...readableIframeDocuments()];
    for (const root of roots) {
      const candidates = [
        ...root.querySelectorAll('input[name*="subject" i], input[id*="subject" i], input[placeholder*="subject" i]'),
      ];
      const found = candidates.find(isVisible);
      if (found) return found;
    }
    return null;
  };
  const findContactBuyerAction = () => {
    const candidates = [...document.querySelectorAll('button, a, [role="button"]')].filter(isVisible);
    return candidates.find((element) => {
      const text = normalizedText(element.innerText || element.textContent || element.getAttribute?.("aria-label"));
      return /^(contact buyer|message buyer|contact customer|message customer)$/.test(text);
    }) || null;
  };
  // The Orders list ("Manage orders") row action menu is the one entry
  // point that reliably resolves -- unlike the order-details deep link,
  // which regularly fails to load at all ("Unfortunately there has been an
  // error retrieving your order"). Its "Message buyer" item sits behind a
  // "Show more actions" toggle and carries hidden accessibility text
  // ("...for order number X"), so it needs its own opener and a
  // starts-with match rather than the exact-text findContactBuyerAction.
  const findMoreActionsToggle = () => {
    const candidates = [...document.querySelectorAll('[aria-label="Show more actions"]')].filter(isVisible);
    return candidates[0] || null;
  };
  const findMessageBuyerMenuItem = () => {
    // The real menu item is a <button> wrapped in an <li> that carries the
    // same text -- querying "button, li" together and taking the first DOM
    // match picks the outer <li> (document order puts it before its own
    // child button), which does not carry the click handler. Buttons must
    // be checked on their own first, ahead of any other element carrying
    // the same visible text.
    const buttons = [...document.querySelectorAll("button")].filter(isVisible);
    const button = buttons.find((element) => normalizedText(element.innerText || element.textContent).startsWith("message buyer"));
    if (button) return button;
    const candidates = [...document.querySelectorAll("li, [role=\"menuitem\"]")].filter(isVisible);
    return candidates.find((element) => {
      const text = normalizedText(element.innerText || element.textContent);
      return text.startsWith("message buyer");
    }) || null;
  };

  const ensureNotice = () => {
    let host = document.getElementById("autozs-customer-message-notice");
    if (host) return host;
    host = document.createElement("div");
    host.id = "autozs-customer-message-notice";
    host.style.cssText = [
      "position:fixed",
      "right:24px",
      "bottom:24px",
      "z-index:2147483647",
      "width:min(420px,calc(100vw - 48px))",
      "padding:18px",
      "border:1px solid #315047",
      "border-radius:10px",
      "background:#111a15",
      "box-shadow:0 18px 55px rgba(0,0,0,.4)",
      "color:#edf4ef",
      "font:14px/1.4 system-ui,-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif",
    ].join(";");
    host.innerHTML = '<strong style="display:block;font-size:18px;margin-bottom:6px">AutoZS customer reply</strong><span>Opening the eBay message composer…</span>';
    (document.body || document.documentElement).appendChild(host);
    return host;
  };
  const setNotice = (text, state = "working") => {
    const host = ensureNotice();
    const accent = state === "ready" ? "#56d88a" : state === "error" ? "#ff7f68" : "#4bb7a6";
    host.style.borderColor = accent;
    const label = host.querySelector("span");
    if (label) label.textContent = text;
  };
  const reportStatus = async (payload) => {
    try {
      return await chrome.runtime.sendMessage({
        type: "autozs-customer-message-status",
        messageId: activeMessageId,
        payload,
      });
    } catch {
      return null;
    }
  };
  const watchForSend = (body) => {
    let sendClicked = false;
    document.addEventListener("click", (event) => {
      const action = event.target?.closest?.('button, [role="button"], input[type="submit"]');
      const text = normalizedText(action?.innerText || action?.value || action?.getAttribute?.("aria-label"));
      if (/^(send|send message|reply)$/.test(text)) sendClicked = true;
    }, true);
    const startedAt = Date.now();
    const timer = setInterval(async () => {
      if (Date.now() - startedAt > 5 * 60 * 1000) {
        clearInterval(timer);
        return;
      }
      if (!sendClicked) return;
      const pageText = normalizedText(document.body?.innerText);
      const explicitSuccess = /message (?:has been |was )?sent|reply (?:has been |was )?sent|sent successfully/.test(pageText);
      const bodyVisible = body.length >= 20 && pageText.includes(normalizedText(body).slice(0, 80));
      const composerStillOpen = Boolean(findComposer());
      if (!explicitSuccess && (composerStillOpen || !bodyVisible)) return;
      clearInterval(timer);
      await reportStatus({ status: "sent", error: null });
      setNotice("Message sent and recorded by AutoZS.", "ready");
    }, 1000);
  };

  (async () => {
    const messageId = initialMessageId || await new Promise((resolve) => {
      const timeout = setTimeout(() => resolve(0), 95 * 1000);
      relayedMessageId.then((candidate) => {
        clearTimeout(timeout);
        resolve(candidate);
      });
    });
    if (!messageId) return;
    activeMessageId = messageId;
    await sleep(250);
    if (isTopFrame) ensureNotice();
    const response = await chrome.runtime.sendMessage({
      type: "autozs-customer-message-payload",
      messageId,
    });
    if (!response?.ok || !response.payload?.message?.body) {
      setNotice(response?.error || "The queued AutoZS reply could not be loaded.", "error");
      return;
    }
    const queued = response.payload.message;
    let clickedContact = false;
    let openedMoreActions = false;
    let clickedMessageBuyer = false;
    const deadline = Date.now() + 90 * 1000;
    while (Date.now() < deadline) {
      if (isTopFrame) relayMessageIdToFrames(messageId);
      const composer = findComposer();
      if (composer) {
        emitInput(composer, String(queued.body || ""));
        const subject = findSubject();
        if (subject && queued.subject) emitInput(subject, String(queued.subject));
        await reportStatus({
          status: "prepared",
          error: "Prepared in the signed-in eBay composer; awaiting your review and manual Send.",
        });
        setNotice("Reply filled. Review the English and Spanish message, then press eBay’s Send button.", "ready");
        watchForSend(String(queued.body || ""));
        return;
      }
      if (!clickedContact) {
        const contact = findContactBuyerAction();
        if (contact) {
          clickedContact = true;
          contact.click();
          setNotice("Opening the buyer message composer…");
        }
      }
      if (!clickedMessageBuyer) {
        const messageBuyerItem = findMessageBuyerMenuItem();
        if (messageBuyerItem) {
          clickedMessageBuyer = true;
          messageBuyerItem.click();
          setNotice("Opening the buyer message panel…");
        } else if (!openedMoreActions) {
          const moreActions = findMoreActionsToggle();
          if (moreActions) {
            openedMoreActions = true;
            moreActions.click();
            setNotice("Opening the order's actions menu…");
          }
        }
      }
      await sleep(500);
    }
    await reportStatus({
      status: "failed",
      error: "AutoZS opened the eBay order but could not locate its buyer message composer.",
    });
    setNotice("AutoZS could not find the message composer. Open Contact buyer on this order and queue the reply again.", "error");
  })().catch(async (error) => {
    await reportStatus({ status: "failed", error: error?.message || String(error) });
    setNotice(`Message preparation stopped: ${error?.message || String(error)}`, "error");
  });
})();
