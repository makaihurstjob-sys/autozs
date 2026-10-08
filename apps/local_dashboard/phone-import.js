(() => {
  const params = new URLSearchParams(location.search);
  const defaultApi = location.hostname.endsWith('.ts.net') ? `${location.protocol}//${location.hostname}:8443` : 'http://127.0.0.1:8000';
  const api = new URL(params.get('api') || defaultApi);
  const allowedHost = api.hostname === location.hostname || ['127.0.0.1', 'localhost'].includes(location.hostname) && ['127.0.0.1', 'localhost'].includes(api.hostname);
  const input = document.getElementById('source-url');
  const submit = document.getElementById('submit');
  const result = document.getElementById('result');
  const feedback = (message, error = false) => { result.textContent = message; result.dataset.error = String(error); };
  const mobile = new URL('/mobile.html', location.origin);
  mobile.searchParams.set('api', api.origin);
  document.getElementById('back').href = mobile.href;
  const shortcut = new URL('/phone-import.html', location.origin);
  shortcut.searchParams.set('api', api.origin);
  const prefix = shortcut.href + '&source=';
  document.getElementById('shortcut-prefix').textContent = prefix;
  input.value = params.get('source') || '';
  // A shared URL fills the form only. Navigation never performs an import.
  if (!allowedHost || (location.protocol === 'https:' && api.protocol !== 'https:')) {
    submit.disabled = true;
    feedback('Open this page from your AUTOZS mobile dashboard so it uses the correct private connection.', true);
  }
  document.getElementById('copy-prefix').addEventListener('click', async () => {
    try { await navigator.clipboard.writeText(prefix); feedback('Shortcut URL prefix copied.'); }
    catch { feedback('Select and copy the URL prefix above.'); }
  });
  document.getElementById('import-form').addEventListener('submit', async event => {
    event.preventDefault();
    if (submit.disabled) return;
    let source;
    try {
      source = new URL(input.value.trim());
      if (source.protocol !== 'https:' || !['homedepot.com', 'www.homedepot.com'].includes(source.hostname)
          || source.username || source.password || !/^\/p\/[^/]+\/\d{9}\/?$/.test(source.pathname)) throw new Error();
    } catch { feedback('Paste the full Home Depot product link from Safari, rather than a search page or short link.', true); return; }
    submit.disabled = true;
    feedback('Saving your draft…');
    try {
      const response = await fetch(api.origin + '/products/phone-import', {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({source_url: source.href}),
        signal: AbortSignal.timeout(30000),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : 'Could not save this draft.');
      feedback(`${data.message}\nProduct #${data.product_id}`);
    } catch (error) {
      feedback(error.name === 'TimeoutError' || error.name === 'TypeError'
        ? 'Could not confirm the save. Check Tailscale and the AUTOZS computer, then try the same link again; existing drafts are kept.'
        : error.message, true);
    } finally { submit.disabled = false; }
  });
})();
