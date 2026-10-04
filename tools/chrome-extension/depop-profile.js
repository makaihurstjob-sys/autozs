(() => {
  if (globalThis.__AUTOZS_DEPOP_PROFILE__) return;
  globalThis.__AUTOZS_DEPOP_PROFILE__ = true;

  function status() {
    const usernames = new Set([...document.querySelectorAll('header a[aria-label="Likes"], nav a[aria-label="Likes"]')].map(link => {
      try {
        const url = new URL(link.href);
        return url.origin === "https://www.depop.com" ? url.pathname.match(/^\/([^/]+)\/likes\/?$/)?.[1]?.toLowerCase() : null;
      } catch { return null; }
    }).filter(Boolean));
    const username = usernames.size === 1 ? [...usernames][0] : null;
    const signedOut = !username || /\/login(?:\/|\?|$)|\/signup(?:\/|\?|$)/i.test(location.href);
    return {
      marketplace: "depop",
      ready: !signedOut,
      signedIn: !signedOut,
      username: signedOut ? null : username,
      url: location.href,
      title: document.title,
      automation: "profile_ready",
    };
  }

  chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
    if (message?.type !== "autozs:depop-profile-status") return undefined;
    sendResponse(status());
    return true;
  });

  document.documentElement.dataset.autozsDepopProfile = status().signedIn ? "signed-in" : "signed-out";
})();
