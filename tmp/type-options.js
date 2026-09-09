({options:[...document.querySelectorAll("[role=menuitemradio],[role=menuitemcheckbox]")].filter(e=>e.getClientRects().length).map(e=>({text:e.innerText,selected:e.getAttribute("aria-checked")}))})
