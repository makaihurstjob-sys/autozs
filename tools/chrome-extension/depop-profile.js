(() => {
  if (globalThis.__AUTOZS_DEPOP_PROFILE__) return;
  globalThis.__AUTOZS_DEPOP_PROFILE__ = true;

  function status() {
    const text = document.body?.innerText || "";
    const signedOut = /log in|sign up/i.test(text) && /depop/i.test(document.title + text.slice(0, 5000));
    return {
      marketplace: "depop",
      ready: !signedOut,
      signedIn: !signedOut,
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
