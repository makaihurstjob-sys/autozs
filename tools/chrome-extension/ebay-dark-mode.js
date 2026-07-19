(async () => {
  const STYLE_ID = "autozs-ebay-dark-mode-style";
  const ROOT_CLASS = "autozs-ebay-dark-mode";
  const LOCAL_API = "https://desktop-56u49jf.tailb2892a.ts.net:8443";
  const DARK_MODE_BUILD = "2026-07-19-myebay-flyout-contrast";
  const existingStyle = document.getElementById(STYLE_ID);
  const existingBuild = existingStyle?.getAttribute?.("data-autozs-build") || "";
  if (window.__autozsEbayDarkModeStarted && existingBuild === DARK_MODE_BUILD) return;
  if (existingStyle) existingStyle.remove();
  window.__autozsEbayDarkModeStarted = true;

  const css = `
    html.${ROOT_CLASS} {
      color-scheme: dark !important;
      background: #101412 !important;
    }
    html.${ROOT_CLASS} body,
    html.${ROOT_CLASS} #mainContent,
    html.${ROOT_CLASS} #CenterPanel,
    html.${ROOT_CLASS} #LeftPanel,
    html.${ROOT_CLASS} #RightPanel,
    html.${ROOT_CLASS} main,
    html.${ROOT_CLASS} section,
    html.${ROOT_CLASS} [role="main"] {
      background: #101412 !important;
      color: #edf4ef !important;
    }
    html.${ROOT_CLASS} #gh,
    html.${ROOT_CLASS} #gh-top,
    html.${ROOT_CLASS} #gh-gb,
    html.${ROOT_CLASS} #gh-cat-box,
    html.${ROOT_CLASS} #gh-ac-box,
    html.${ROOT_CLASS} header,
    html.${ROOT_CLASS} nav,
    html.${ROOT_CLASS} [class*="header" i],
    html.${ROOT_CLASS} [class*="nav" i] {
      background: #171d1a !important;
      border-color: #2b352f !important;
      color: #edf4ef !important;
    }
    html.${ROOT_CLASS} #gh-eb-My-o,
    html.${ROOT_CLASS} #gh-eb-My [role="menu"],
    html.${ROOT_CLASS} #gh [data-menu-name="my-ebay"],
    html.${ROOT_CLASS} #gh [aria-label*="My eBay" i][role="menu"],
    html.${ROOT_CLASS} #gh [class*="myebay" i] {
      background: #171d1a !important;
      background-color: #171d1a !important;
      border-color: #35423b !important;
      color: #edf4ef !important;
      box-shadow: 0 18px 42px rgba(0, 0, 0, .48) !important;
    }
    html.${ROOT_CLASS} #gh-eb-My-o *,
    html.${ROOT_CLASS} #gh-eb-My [role="menu"] *,
    html.${ROOT_CLASS} #gh [data-menu-name="my-ebay"] *,
    html.${ROOT_CLASS} #gh [aria-label*="My eBay" i][role="menu"] *,
    html.${ROOT_CLASS} #gh [class*="myebay" i] * {
      background: transparent !important;
      background-color: transparent !important;
      border-color: #2b352f !important;
      color: #edf4ef !important;
    }
    html.${ROOT_CLASS} #gh-eb-My-o a,
    html.${ROOT_CLASS} #gh-eb-My-o a span,
    html.${ROOT_CLASS} #gh-eb-My [role="menu"] a,
    html.${ROOT_CLASS} #gh-eb-My [role="menu"] a span,
    html.${ROOT_CLASS} #gh [data-menu-name="my-ebay"] a,
    html.${ROOT_CLASS} #gh [data-menu-name="my-ebay"] a span,
    html.${ROOT_CLASS} #gh [class*="myebay" i] a,
    html.${ROOT_CLASS} #gh [class*="myebay" i] a span {
      color: #a7e5db !important;
    }
    html.${ROOT_CLASS} #gh-eb-My-o li:hover,
    html.${ROOT_CLASS} #gh-eb-My-o a:hover,
    html.${ROOT_CLASS} #gh-eb-My [role="menu"] li:hover,
    html.${ROOT_CLASS} #gh-eb-My [role="menu"] a:hover,
    html.${ROOT_CLASS} #gh [data-menu-name="my-ebay"] li:hover,
    html.${ROOT_CLASS} #gh [data-menu-name="my-ebay"] a:hover,
    html.${ROOT_CLASS} #gh [class*="myebay" i] li:hover,
    html.${ROOT_CLASS} #gh [class*="myebay" i] a:hover {
      background: #25312b !important;
      background-color: #25312b !important;
      color: #ffffff !important;
    }
    html.${ROOT_CLASS} div,
    html.${ROOT_CLASS} li,
    html.${ROOT_CLASS} ul,
    html.${ROOT_CLASS} ol,
    html.${ROOT_CLASS} table,
    html.${ROOT_CLASS} tr,
    html.${ROOT_CLASS} td,
    html.${ROOT_CLASS} th,
    html.${ROOT_CLASS} fieldset,
    html.${ROOT_CLASS} form,
    html.${ROOT_CLASS} [class*="card" i],
    html.${ROOT_CLASS} [class*="panel" i],
    html.${ROOT_CLASS} [class*="container" i],
    html.${ROOT_CLASS} [class*="module" i],
    html.${ROOT_CLASS} [class*="section" i],
    html.${ROOT_CLASS} [class*="drawer" i],
    html.${ROOT_CLASS} [class*="dialog" i],
    html.${ROOT_CLASS} [class*="modal" i],
    html.${ROOT_CLASS} [class*="menu" i] {
      border-color: #2b352f !important;
    }
    html.${ROOT_CLASS} [class*="card" i],
    html.${ROOT_CLASS} [class*="panel" i],
    html.${ROOT_CLASS} [class*="module" i],
    html.${ROOT_CLASS} [class*="dialog" i],
    html.${ROOT_CLASS} [class*="modal" i],
    html.${ROOT_CLASS} [class*="menu" i],
    html.${ROOT_CLASS} [class*="overlay" i],
    html.${ROOT_CLASS} [class*="popover" i],
    html.${ROOT_CLASS} [class*="flyout" i],
    html.${ROOT_CLASS} [class*="tooltip" i],
    html.${ROOT_CLASS} [class*="infotip" i],
    html.${ROOT_CLASS} [class*="x-overlay" i] {
      background-color: #171d1a !important;
      color: #edf4ef !important;
      box-shadow: 0 16px 42px rgba(0, 0, 0, .35) !important;
    }
    html.${ROOT_CLASS} .lightbox-dialog--hide,
    html.${ROOT_CLASS} .lightbox-dialog[aria-hidden="true"],
    html.${ROOT_CLASS} .ux-overlay[aria-hidden="true"],
    html.${ROOT_CLASS} [class*="dialog" i][aria-hidden="true"],
    html.${ROOT_CLASS} [class*="overlay" i][aria-hidden="true"],
    html.${ROOT_CLASS} [class*="modal" i][aria-hidden="true"] {
      display: none !important;
      opacity: 0 !important;
      pointer-events: none !important;
      visibility: hidden !important;
    }
    html.${ROOT_CLASS} .x-evo-overlay-river-iframe,
    html.${ROOT_CLASS} .x-evo-overlay-river-iframe .lightbox-dialog__window,
    html.${ROOT_CLASS} .x-evo-overlay-river-iframe .lightbox-dialog__main,
    html.${ROOT_CLASS} .x-evo-overlay-river-iframe .ux-overlay__content,
    html.${ROOT_CLASS} iframe[title*="Traffic Report" i] {
      background: #171d1a !important;
      background-color: #171d1a !important;
      color: #edf4ef !important;
    }
    html.${ROOT_CLASS} h1,
    html.${ROOT_CLASS} h2,
    html.${ROOT_CLASS} h3,
    html.${ROOT_CLASS} h4,
    html.${ROOT_CLASS} h5,
    html.${ROOT_CLASS} h6,
    html.${ROOT_CLASS} p,
    html.${ROOT_CLASS} span,
    html.${ROOT_CLASS} label,
    html.${ROOT_CLASS} strong,
    html.${ROOT_CLASS} b,
    html.${ROOT_CLASS} small,
    html.${ROOT_CLASS} dt,
    html.${ROOT_CLASS} dd,
    html.${ROOT_CLASS} legend,
    html.${ROOT_CLASS} button,
    html.${ROOT_CLASS} [role="button"] {
      color: inherit !important;
    }
    html.${ROOT_CLASS} a,
    html.${ROOT_CLASS} a span {
      color: #8ed8cc !important;
    }
    html.${ROOT_CLASS} a:visited,
    html.${ROOT_CLASS} a:visited span {
      color: #b8d9d3 !important;
    }
    html.${ROOT_CLASS} input,
    html.${ROOT_CLASS} textarea,
    html.${ROOT_CLASS} select,
    html.${ROOT_CLASS} [contenteditable="true"],
    html.${ROOT_CLASS} [role="textbox"],
    html.${ROOT_CLASS} .textbox__control,
    html.${ROOT_CLASS} .select__control {
      background: #101412 !important;
      border-color: #2b352f !important;
      color: #edf4ef !important;
      caret-color: #4bb7a6 !important;
    }
    html.${ROOT_CLASS} input::placeholder,
    html.${ROOT_CLASS} textarea::placeholder {
      color: #9aa89f !important;
    }
    html.${ROOT_CLASS} button,
    html.${ROOT_CLASS} .btn,
    html.${ROOT_CLASS} [class*="button" i],
    html.${ROOT_CLASS} [role="button"] {
      border-color: #2b352f !important;
    }
    html.${ROOT_CLASS} button:not([disabled]):hover,
    html.${ROOT_CLASS} [role="button"]:not([disabled]):hover,
    html.${ROOT_CLASS} a:hover {
      filter: brightness(1.08) !important;
    }
    html.${ROOT_CLASS} hr,
    html.${ROOT_CLASS} .separator,
    html.${ROOT_CLASS} [class*="divider" i],
    html.${ROOT_CLASS} [class*="border" i] {
      border-color: #2b352f !important;
    }
    html.${ROOT_CLASS} svg,
    html.${ROOT_CLASS} svg path,
    html.${ROOT_CLASS} svg circle,
    html.${ROOT_CLASS} svg rect {
      color: inherit;
    }
    html.${ROOT_CLASS} img,
    html.${ROOT_CLASS} picture,
    html.${ROOT_CLASS} video,
    html.${ROOT_CLASS} canvas {
      filter: none !important;
    }
    html.${ROOT_CLASS} [style*="background-color: rgb(255, 255, 255)"],
    html.${ROOT_CLASS} [style*="background: rgb(255, 255, 255)"],
    html.${ROOT_CLASS} [style*="background-color:#fff"],
    html.${ROOT_CLASS} [style*="background:#fff"],
    html.${ROOT_CLASS} [style*="background-color: white"],
    html.${ROOT_CLASS} [style*="background: white"] {
      background-color: #171d1a !important;
    }
    html.${ROOT_CLASS} [style*="color: rgb(0, 0, 0)"],
    html.${ROOT_CLASS} [style*="color:#000"],
    html.${ROOT_CLASS} [style*="color: black"] {
      color: #edf4ef !important;
    }
    html.${ROOT_CLASS} .srp-results,
    html.${ROOT_CLASS} .srp-results ul,
    html.${ROOT_CLASS} .srp-results li,
    html.${ROOT_CLASS} .s-item,
    html.${ROOT_CLASS} .s-item__wrapper,
    html.${ROOT_CLASS} .s-item__image-section,
    html.${ROOT_CLASS} .s-item__info,
    html.${ROOT_CLASS} .s-item__details,
    html.${ROOT_CLASS} .s-item__detail,
    html.${ROOT_CLASS} .s-item__purchase-options-with-icon,
    html.${ROOT_CLASS} .s-item__seller-info,
    html.${ROOT_CLASS} .s-item__subtitle,
    html.${ROOT_CLASS} .s-item__dynamic,
    html.${ROOT_CLASS} .s-item__caption,
    html.${ROOT_CLASS} .s-item__sep,
    html.${ROOT_CLASS} .srp-list,
    html.${ROOT_CLASS} .srp-river-results,
    html.${ROOT_CLASS} .srp-river-answer,
    html.${ROOT_CLASS} .srp-controls,
    html.${ROOT_CLASS} .srp-controls__control,
    html.${ROOT_CLASS} .srp-save-null-search,
    html.${ROOT_CLASS} .srp-main,
    html.${ROOT_CLASS} .srp-left-rail,
    html.${ROOT_CLASS} .srp-refine__category__list,
    html.${ROOT_CLASS} .srp-refine__item,
    html.${ROOT_CLASS} .x-refine__main__list,
    html.${ROOT_CLASS} .x-refine__main__list *,
    html.${ROOT_CLASS} .x-refine__select__svg,
    html.${ROOT_CLASS} .x-refine__multi-select,
    html.${ROOT_CLASS} .x-refine__multi-select *,
    html.${ROOT_CLASS} .x-flyout,
    html.${ROOT_CLASS} .x-flyout__button,
    html.${ROOT_CLASS} .x-flyout__button *,
    html.${ROOT_CLASS} .x-tray,
    html.${ROOT_CLASS} .x-tray__slider,
    html.${ROOT_CLASS} .fake-tabs,
    html.${ROOT_CLASS} .fake-tabs__items,
    html.${ROOT_CLASS} .fake-tabs__item {
      background: transparent !important;
      background-color: transparent !important;
      box-shadow: none !important;
    }
    html.${ROOT_CLASS} .s-item,
    html.${ROOT_CLASS} .srp-river-answer,
    html.${ROOT_CLASS} .srp-results .brwrvr__item-card {
      border-bottom: 1px solid #2b352f !important;
    }
    html.${ROOT_CLASS} .s-item:hover,
    html.${ROOT_CLASS} .s-item:hover .s-item__wrapper {
      background-color: #131916 !important;
    }
    html.${ROOT_CLASS} .s-item__title,
    html.${ROOT_CLASS} .s-item__title span,
    html.${ROOT_CLASS} a .s-item__title,
    html.${ROOT_CLASS} a:visited .s-item__title,
    html.${ROOT_CLASS} .s-item a[href*="/itm/"],
    html.${ROOT_CLASS} .s-item a[href*="/itm/"] span,
    html.${ROOT_CLASS} .s-item__link,
    html.${ROOT_CLASS} .s-item__link:visited {
      color: #edf4ef !important;
    }
    html.${ROOT_CLASS} .s-item__price,
    html.${ROOT_CLASS} .s-item__price span {
      color: #ffffff !important;
    }
    html.${ROOT_CLASS} .s-item__subtitle,
    html.${ROOT_CLASS} .s-item__location,
    html.${ROOT_CLASS} .s-item__shipping,
    html.${ROOT_CLASS} .s-item__purchase-options-with-icon,
    html.${ROOT_CLASS} .s-item__seller-info,
    html.${ROOT_CLASS} .s-item__dynamic,
    html.${ROOT_CLASS} .s-item__caption {
      color: #c7d2cc !important;
    }
    html.${ROOT_CLASS} .s-item__image-wrapper,
    html.${ROOT_CLASS} .s-item__image,
    html.${ROOT_CLASS} .s-item__image img {
      background-color: #ffffff !important;
    }
    html.${ROOT_CLASS} #gh-ac-box,
    html.${ROOT_CLASS} #gh-ac-box *,
    html.${ROOT_CLASS} #gh-ac-ul,
    html.${ROOT_CLASS} #gh-ac-ul *,
    html.${ROOT_CLASS} #gh-ac,
    html.${ROOT_CLASS} #gh-ac-box2,
    html.${ROOT_CLASS} #gh [role="listbox"],
    html.${ROOT_CLASS} #gh [role="listbox"] *,
    html.${ROOT_CLASS} header [role="listbox"],
    html.${ROOT_CLASS} header [role="listbox"] *,
    html.${ROOT_CLASS} [id^="gh-ac" i],
    html.${ROOT_CLASS} [id^="gh-ac" i] *,
    html.${ROOT_CLASS} [class*="autosuggest" i],
    html.${ROOT_CLASS} [class*="autosuggest" i] *,
    html.${ROOT_CLASS} [class*="autocomplete" i],
    html.${ROOT_CLASS} [class*="autocomplete" i] *,
    html.${ROOT_CLASS} [class*="typeahead" i],
    html.${ROOT_CLASS} [class*="typeahead" i] *,
    html.${ROOT_CLASS} [class*="suggestion" i],
    html.${ROOT_CLASS} [class*="suggestion" i] * {
      color: #edf4ef !important;
      opacity: 1 !important;
    }
    html.${ROOT_CLASS} #gh-ac-box,
    html.${ROOT_CLASS} #gh-ac-ul,
    html.${ROOT_CLASS} #gh [role="listbox"],
    html.${ROOT_CLASS} header [role="listbox"],
    html.${ROOT_CLASS} [id^="gh-ac" i][role="listbox"],
    html.${ROOT_CLASS} [id^="gh-ac" i] [role="listbox"],
    html.${ROOT_CLASS} [class*="autosuggest" i],
    html.${ROOT_CLASS} [class*="autocomplete" i],
    html.${ROOT_CLASS} [class*="typeahead" i] {
      background: #101412 !important;
      background-color: #101412 !important;
      border-color: #2b352f !important;
      box-shadow: 0 24px 54px rgba(0, 0, 0, .52) !important;
      color: #edf4ef !important;
    }
    html.${ROOT_CLASS} #gh-ac-box li,
    html.${ROOT_CLASS} #gh-ac-ul li,
    html.${ROOT_CLASS} #gh [role="listbox"] li,
    html.${ROOT_CLASS} #gh [role="listbox"] [role="option"],
    html.${ROOT_CLASS} header [role="listbox"] li,
    html.${ROOT_CLASS} header [role="listbox"] [role="option"],
    html.${ROOT_CLASS} [id^="gh-ac" i] li,
    html.${ROOT_CLASS} [id^="gh-ac" i] [role="option"],
    html.${ROOT_CLASS} [class*="autosuggest" i] li,
    html.${ROOT_CLASS} [class*="autocomplete" i] li,
    html.${ROOT_CLASS} [class*="typeahead" i] li,
    html.${ROOT_CLASS} [class*="suggestion" i] li,
    html.${ROOT_CLASS} [class*="suggestion" i] [role="option"] {
      background: #101412 !important;
      background-color: #101412 !important;
      border-color: #22312b !important;
      color: #edf4ef !important;
    }
    html.${ROOT_CLASS} #gh-ac-box li:hover,
    html.${ROOT_CLASS} #gh-ac-ul li:hover,
    html.${ROOT_CLASS} #gh [role="listbox"] li:hover,
    html.${ROOT_CLASS} #gh [role="listbox"] [role="option"]:hover,
    html.${ROOT_CLASS} #gh [role="listbox"] [aria-selected="true"],
    html.${ROOT_CLASS} header [role="listbox"] li:hover,
    html.${ROOT_CLASS} header [role="listbox"] [role="option"]:hover,
    html.${ROOT_CLASS} header [role="listbox"] [aria-selected="true"],
    html.${ROOT_CLASS} [id^="gh-ac" i] li:hover,
    html.${ROOT_CLASS} [id^="gh-ac" i] [role="option"]:hover,
    html.${ROOT_CLASS} [id^="gh-ac" i] [aria-selected="true"],
    html.${ROOT_CLASS} [class*="autosuggest" i] li:hover,
    html.${ROOT_CLASS} [class*="autocomplete" i] li:hover,
    html.${ROOT_CLASS} [class*="typeahead" i] li:hover,
    html.${ROOT_CLASS} [class*="suggestion" i] li:hover,
    html.${ROOT_CLASS} [class*="suggestion" i] [role="option"]:hover {
      background: #1d2b26 !important;
      background-color: #1d2b26 !important;
      color: #ffffff !important;
    }
    html.${ROOT_CLASS} #gh-ac-box svg,
    html.${ROOT_CLASS} #gh-ac-box path,
    html.${ROOT_CLASS} #gh-ac-ul svg,
    html.${ROOT_CLASS} #gh-ac-ul path,
    html.${ROOT_CLASS} #gh [role="listbox"] svg,
    html.${ROOT_CLASS} #gh [role="listbox"] path,
    html.${ROOT_CLASS} header [role="listbox"] svg,
    html.${ROOT_CLASS} header [role="listbox"] path,
    html.${ROOT_CLASS} [id^="gh-ac" i] svg,
    html.${ROOT_CLASS} [id^="gh-ac" i] path,
    html.${ROOT_CLASS} [class*="suggestion" i] svg,
    html.${ROOT_CLASS} [class*="suggestion" i] path {
      color: #8ed8cc !important;
      fill: none !important;
      opacity: 1 !important;
      stroke: #8ed8cc !important;
    }
    html.${ROOT_CLASS} #gh-ac-box button,
    html.${ROOT_CLASS} #gh-ac-ul button,
    html.${ROOT_CLASS} #gh [role="listbox"] button,
    html.${ROOT_CLASS} header [role="listbox"] button,
    html.${ROOT_CLASS} [id^="gh-ac" i] button,
    html.${ROOT_CLASS} [class*="suggestion" i] button {
      background: transparent !important;
      border-color: transparent !important;
      color: #9aa89f !important;
      opacity: 1 !important;
    }
    html.${ROOT_CLASS} .x-refine__item,
    html.${ROOT_CLASS} .x-refine__item *,
    html.${ROOT_CLASS} .srp-refine__item,
    html.${ROOT_CLASS} .srp-refine__item * {
      color: #8ed8cc !important;
    }
    html.${ROOT_CLASS}.autozs-ebay-listing-editor .textbox,
    html.${ROOT_CLASS}.autozs-ebay-listing-editor .textbox__control,
    html.${ROOT_CLASS}.autozs-ebay-listing-editor .listbox-button__control,
    html.${ROOT_CLASS}.autozs-ebay-listing-editor .se-rte__button-group,
    html.${ROOT_CLASS}.autozs-ebay-listing-editor .summary-container,
    html.${ROOT_CLASS}.autozs-ebay-listing-editor .summary-container-main,
    html.${ROOT_CLASS}.autozs-ebay-listing-editor .summary__legal-faq,
    html.${ROOT_CLASS}.autozs-ebay-listing-editor .aggregate-metric,
    html.${ROOT_CLASS}.autozs-ebay-listing-editor .metric-title {
      background: #171d1a !important;
      background-color: #171d1a !important;
      border-color: #3a4840 !important;
      color: #edf4ef !important;
    }
    html.${ROOT_CLASS}.autozs-ebay-listing-editor .listbox-button__control,
    html.${ROOT_CLASS}.autozs-ebay-listing-editor .listbox-button__control .btn__cell,
    html.${ROOT_CLASS}.autozs-ebay-listing-editor .listbox-button__control .btn__text,
    html.${ROOT_CLASS}.autozs-ebay-listing-editor .service-details__add-services,
    html.${ROOT_CLASS}.autozs-ebay-listing-editor .service-details__add-services *,
    html.${ROOT_CLASS}.autozs-ebay-listing-editor .se-rte__button-group .icon-btn,
    html.${ROOT_CLASS}.autozs-ebay-listing-editor .se-rte__button-group .icon-btn * {
      background-color: #25312b !important;
      border-color: #3a4840 !important;
      color: #edf4ef !important;
      fill: currentColor !important;
      opacity: 1 !important;
      stroke: currentColor !important;
    }
    html.${ROOT_CLASS}.autozs-ebay-listing-editor .listbox-button__control:hover,
    html.${ROOT_CLASS}.autozs-ebay-listing-editor .service-details__add-services:hover,
    html.${ROOT_CLASS}.autozs-ebay-listing-editor .se-rte__button-group .icon-btn:not([disabled]):hover {
      background-color: #304139 !important;
    }
    html.${ROOT_CLASS}.autozs-ebay-listing-editor button[disabled],
    html.${ROOT_CLASS}.autozs-ebay-listing-editor button[disabled] * {
      color: #c2cec7 !important;
      opacity: .72 !important;
    }
    html.${ROOT_CLASS}.autozs-ebay-listing-editor .summary__attributes--label,
    html.${ROOT_CLASS}.autozs-ebay-listing-editor .summary__attributes--label *,
    html.${ROOT_CLASS}.autozs-ebay-listing-editor .summary-container *,
    html.${ROOT_CLASS}.autozs-ebay-listing-editor .summary__legal-faq,
    html.${ROOT_CLASS}.autozs-ebay-listing-editor .summary__legal-faq * {
      color: #edf4ef !important;
      opacity: 1 !important;
    }
    html.${ROOT_CLASS}.autozs-ebay-listing-editor .summary-container a,
    html.${ROOT_CLASS}.autozs-ebay-listing-editor .summary-container button.fake-link,
    html.${ROOT_CLASS}.autozs-ebay-listing-editor .summary__legal-faq a {
      color: #8ed8cc !important;
    }
    html.${ROOT_CLASS}.autozs-ebay-listing-editor .se-textbox--counter,
    html.${ROOT_CLASS}.autozs-ebay-listing-editor .se-textarea--counter,
    html.${ROOT_CLASS}.autozs-ebay-listing-editor [class*="helper" i],
    html.${ROOT_CLASS}.autozs-ebay-listing-editor [class*="subtitle" i] {
      color: #b8c5bd !important;
      opacity: 1 !important;
    }
    html.${ROOT_CLASS}.autozs-ebay-listing-editor .uploader-thumbnails-ux__image,
    html.${ROOT_CLASS}.autozs-ebay-listing-editor .uploader-thumbnails-ux__image * {
      color: #17201b !important;
      fill: currentColor !important;
      stroke: currentColor !important;
    }
    html.${ROOT_CLASS}.autozs-ebay-listing-editor .uploader-thumbnails-ux__image:not([id]),
    html.${ROOT_CLASS}.autozs-ebay-listing-editor .uploader-thumbnails-ux__image:not([id]) .uploader-thumbnails-ux-image-guidance,
    html.${ROOT_CLASS}.autozs-ebay-listing-editor .uploader-thumbnails-ux__image:not([id]) * {
      background: #1b2420 !important;
      background-color: #1b2420 !important;
      border-color: #3a4840 !important;
      color: #dce7e0 !important;
      fill: currentColor !important;
      stroke: currentColor !important;
    }
    html.${ROOT_CLASS}.autozs-ebay-listing-editor .listbox__options,
    html.${ROOT_CLASS}.autozs-ebay-listing-editor [role="listbox"],
    html.${ROOT_CLASS}.autozs-ebay-listing-editor [role="menu"] {
      background: #171d1a !important;
      background-color: #171d1a !important;
      border-color: #3a4840 !important;
      box-shadow: 0 18px 44px rgba(0, 0, 0, .48) !important;
      color: #edf4ef !important;
    }
    html.${ROOT_CLASS}.autozs-ebay-listing-editor .listbox__option,
    html.${ROOT_CLASS}.autozs-ebay-listing-editor .listbox__value,
    html.${ROOT_CLASS}.autozs-ebay-listing-editor [role="option"],
    html.${ROOT_CLASS}.autozs-ebay-listing-editor [role="option"] *,
    html.${ROOT_CLASS}.autozs-ebay-listing-editor [role="menuitemradio"],
    html.${ROOT_CLASS}.autozs-ebay-listing-editor [role="menuitemradio"] * {
      background-color: transparent !important;
      color: #edf4ef !important;
      fill: currentColor !important;
      opacity: 1 !important;
      stroke: currentColor !important;
    }
    html.${ROOT_CLASS}.autozs-ebay-listing-editor .listbox__option:hover,
    html.${ROOT_CLASS}.autozs-ebay-listing-editor .listbox__option--active,
    html.${ROOT_CLASS}.autozs-ebay-listing-editor [role="option"]:hover,
    html.${ROOT_CLASS}.autozs-ebay-listing-editor [role="option"][aria-selected="true"],
    html.${ROOT_CLASS}.autozs-ebay-listing-editor [role="menuitemradio"]:hover,
    html.${ROOT_CLASS}.autozs-ebay-listing-editor [role="menuitemradio"][aria-checked="true"] {
      background-color: #25352e !important;
      color: #ffffff !important;
    }
    html.${ROOT_CLASS}.autozs-ebay-listing-editor .dp-container,
    html.${ROOT_CLASS}.autozs-ebay-listing-editor .date-picker {
      background: #171d1a !important;
      background-color: #171d1a !important;
      border-color: #3a4840 !important;
      box-shadow: 0 18px 44px rgba(0, 0, 0, .48) !important;
      color: #edf4ef !important;
    }
    html.${ROOT_CLASS}.autozs-ebay-listing-editor .date-picker button:not([disabled]) {
      color: #9be1d5 !important;
      opacity: 1 !important;
    }
    html.${ROOT_CLASS}.autozs-ebay-listing-editor .date-picker button[disabled] {
      color: #829087 !important;
      opacity: 1 !important;
    }
    html.${ROOT_CLASS}.autozs-ebay-listing-editor .date-picker .day.today button {
      outline: 1px solid #6bc9ba !important;
      outline-offset: -2px !important;
    }
    html.${ROOT_CLASS}.autozs-ebay-listing-editor .date-picker .day.selected,
    html.${ROOT_CLASS}.autozs-ebay-listing-editor .date-picker .day.selected button {
      background: #0064d2 !important;
      background-color: #0064d2 !important;
      color: #ffffff !important;
    }
    html.${ROOT_CLASS}.autozs-ebay-listing-editor .btn--primary,
    html.${ROOT_CLASS}.autozs-ebay-listing-editor .btn--primary * {
      background-color: #0064d2 !important;
      border-color: #0064d2 !important;
      color: #ffffff !important;
    }
    html.${ROOT_CLASS}.autozs-ebay-listing-editor .gh-a11y-skip-button__link {
      background: #171d1a !important;
      border-color: #6bc9ba !important;
      color: #9be1d5 !important;
    }
    html.${ROOT_CLASS}.autozs-ebay-prelist body,
    html.${ROOT_CLASS}.autozs-ebay-prelist main,
    html.${ROOT_CLASS}.autozs-ebay-prelist #mainContent,
    html.${ROOT_CLASS}.autozs-ebay-prelist footer,
    html.${ROOT_CLASS}.autozs-ebay-prelist [role="contentinfo"],
    html.${ROOT_CLASS}.autozs-ebay-prelist [class*="footer" i] {
      background: #101412 !important;
      background-color: #101412 !important;
      border-color: #2b352f !important;
      color: #edf4ef !important;
    }
    html.${ROOT_CLASS}.autozs-ebay-prelist footer *,
    html.${ROOT_CLASS}.autozs-ebay-prelist [role="contentinfo"] *,
    html.${ROOT_CLASS}.autozs-ebay-prelist [class*="footer" i] * {
      border-color: #3a4840 !important;
      color: #b8c5bd !important;
      opacity: 1 !important;
    }
    html.${ROOT_CLASS}.autozs-ebay-prelist footer a,
    html.${ROOT_CLASS}.autozs-ebay-prelist footer a *,
    html.${ROOT_CLASS}.autozs-ebay-prelist [role="contentinfo"] a,
    html.${ROOT_CLASS}.autozs-ebay-prelist [role="contentinfo"] a *,
    html.${ROOT_CLASS}.autozs-ebay-prelist button.fake-link,
    html.${ROOT_CLASS}.autozs-ebay-prelist button[aria-label*="category" i] {
      color: #8ed8cc !important;
      opacity: 1 !important;
    }
    html.${ROOT_CLASS}.autozs-ebay-prelist button[disabled],
    html.${ROOT_CLASS}.autozs-ebay-prelist button[aria-disabled="true"],
    html.${ROOT_CLASS}.autozs-ebay-prelist [role="button"][aria-disabled="true"] {
      background: #1d2521 !important;
      background-color: #1d2521 !important;
      border-color: #48574f !important;
      color: #aebbb4 !important;
      opacity: 1 !important;
    }
    html.${ROOT_CLASS}.autozs-ebay-prelist button[disabled] *,
    html.${ROOT_CLASS}.autozs-ebay-prelist button[aria-disabled="true"] *,
    html.${ROOT_CLASS}.autozs-ebay-prelist [role="button"][aria-disabled="true"] * {
      color: #aebbb4 !important;
      opacity: 1 !important;
    }
    html.${ROOT_CLASS}.autozs-ebay-prelist [role="dialog"],
    html.${ROOT_CLASS}.autozs-ebay-prelist [role="listbox"],
    html.${ROOT_CLASS}.autozs-ebay-prelist [role="menu"] {
      background: #171d1a !important;
      background-color: #171d1a !important;
      border-color: #3a4840 !important;
      color: #edf4ef !important;
    }
    html.${ROOT_CLASS}.autozs-ebay-seller-hub body,
    html.${ROOT_CLASS}.autozs-ebay-seller-hub main,
    html.${ROOT_CLASS}.autozs-ebay-seller-hub #mainContent,
    html.${ROOT_CLASS}.autozs-ebay-seller-hub .app-shell,
    html.${ROOT_CLASS}.autozs-ebay-seller-hub .page-container,
    html.${ROOT_CLASS}.autozs-ebay-seller-hub .sh-core-layout,
    html.${ROOT_CLASS}.autozs-ebay-seller-hub .sh-core-main,
    html.${ROOT_CLASS}.autozs-ebay-seller-hub .shui-page,
    html.${ROOT_CLASS}.autozs-ebay-seller-hub .shui-page__body,
    html.${ROOT_CLASS}.autozs-ebay-seller-hub .shui-dt-container,
    html.${ROOT_CLASS}.autozs-ebay-seller-hub .shui-dt,
    html.${ROOT_CLASS}.autozs-ebay-seller-hub .shui-dt__grid,
    html.${ROOT_CLASS}.autozs-ebay-seller-hub .shui-dt__viewport,
    html.${ROOT_CLASS}.autozs-ebay-seller-hub .shui-dt__table,
    html.${ROOT_CLASS}.autozs-ebay-seller-hub .shui-dt__body,
    html.${ROOT_CLASS}.autozs-ebay-seller-hub .shui-dt tbody,
    html.${ROOT_CLASS}.autozs-ebay-seller-hub .shui-dt tr,
    html.${ROOT_CLASS}.autozs-ebay-seller-hub .shui-dt td,
    html.${ROOT_CLASS}.autozs-ebay-seller-hub .grid-content,
    html.${ROOT_CLASS}.autozs-ebay-seller-hub .grid-container,
    html.${ROOT_CLASS}.autozs-ebay-seller-hub .grid-wrapper,
    html.${ROOT_CLASS}.autozs-ebay-seller-hub .results-table,
    html.${ROOT_CLASS}.autozs-ebay-seller-hub .lst-grid,
    html.${ROOT_CLASS}.autozs-ebay-seller-hub .listings-grid {
      background: #101412 !important;
      background-color: #101412 !important;
      border-color: #2b352f !important;
      color: #edf4ef !important;
    }
    html.${ROOT_CLASS}.autozs-ebay-seller-hub .shui-dt thead,
    html.${ROOT_CLASS}.autozs-ebay-seller-hub .shui-dt th,
    html.${ROOT_CLASS}.autozs-ebay-seller-hub .shui-dt [class*="shui-dt-column" i],
    html.${ROOT_CLASS}.autozs-ebay-seller-hub .shui-dt [class*="shui-dt--selector" i],
    html.${ROOT_CLASS}.autozs-ebay-seller-hub .header-sentinel,
    html.${ROOT_CLASS}.autozs-ebay-seller-hub .header-row,
    html.${ROOT_CLASS}.autozs-ebay-seller-hub .th-title-text,
    html.${ROOT_CLASS}.autozs-ebay-seller-hub [class*="column__" i],
    html.${ROOT_CLASS}.autozs-ebay-seller-hub [class*="table-header" i] {
      background: #171d1a !important;
      background-color: #171d1a !important;
      border-color: #2b352f !important;
      color: #edf4ef !important;
    }
    html.${ROOT_CLASS}.autozs-ebay-seller-hub .shui-dt th *,
    html.${ROOT_CLASS}.autozs-ebay-seller-hub .shui-dt td *,
    html.${ROOT_CLASS}.autozs-ebay-seller-hub .grid-summary-bar,
    html.${ROOT_CLASS}.autozs-ebay-seller-hub .grid-summary-bar *,
    html.${ROOT_CLASS}.autozs-ebay-seller-hub .grid-summary-bar__label,
    html.${ROOT_CLASS}.autozs-ebay-seller-hub .grid-summary-bar__data,
    html.${ROOT_CLASS}.autozs-ebay-seller-hub .item,
    html.${ROOT_CLASS}.autozs-ebay-seller-hub .item *,
    html.${ROOT_CLASS}.autozs-ebay-seller-hub .gf-legal,
    html.${ROOT_CLASS}.autozs-ebay-seller-hub .gf-legal *,
    html.${ROOT_CLASS}.autozs-ebay-seller-hub #glbfooter,
    html.${ROOT_CLASS}.autozs-ebay-seller-hub #glbfooter *,
    html.${ROOT_CLASS}.autozs-ebay-seller-hub .gh-footer,
    html.${ROOT_CLASS}.autozs-ebay-seller-hub .gh-footer * {
      color: #edf4ef !important;
      opacity: 1 !important;
    }
    html.${ROOT_CLASS}.autozs-ebay-seller-hub .grid-summary-bar,
    html.${ROOT_CLASS}.autozs-ebay-seller-hub .grid-summary-bar .item,
    html.${ROOT_CLASS}.autozs-ebay-seller-hub .bulk-actions,
    html.${ROOT_CLASS}.autozs-ebay-seller-hub .shui-dt-toolbar,
    html.${ROOT_CLASS}.autozs-ebay-seller-hub .shui-dt__toolbar,
    html.${ROOT_CLASS}.autozs-ebay-seller-hub .filter-bar {
      background: transparent !important;
      background-color: transparent !important;
      border-color: #2b352f !important;
    }
    html.${ROOT_CLASS}.autozs-ebay-seller-hub .ifh-content {
      background: #17201b !important;
      background-color: #17201b !important;
      border-color: #2b352f !important;
      color: #edf4ef !important;
    }
    html.${ROOT_CLASS}.autozs-ebay-seller-hub .textbox,
    html.${ROOT_CLASS}.autozs-ebay-seller-hub .textbox *,
    html.${ROOT_CLASS}.autozs-ebay-seller-hub .search-box,
    html.${ROOT_CLASS}.autozs-ebay-seller-hub .search-box *,
    html.${ROOT_CLASS}.autozs-ebay-seller-hub .filter-menu,
    html.${ROOT_CLASS}.autozs-ebay-seller-hub .filter-menu *,
    html.${ROOT_CLASS}.autozs-ebay-seller-hub .menu-button,
    html.${ROOT_CLASS}.autozs-ebay-seller-hub .menu-button * {
      background-color: #101412 !important;
      border-color: #2b352f !important;
      color: #edf4ef !important;
    }
    html.${ROOT_CLASS}.autozs-ebay-seller-hub .shui-dt button,
    html.${ROOT_CLASS}.autozs-ebay-seller-hub .shui-dt .btn,
    html.${ROOT_CLASS}.autozs-ebay-seller-hub .shui-dt .icon-btn,
    html.${ROOT_CLASS}.autozs-ebay-seller-hub .icon-btn,
    html.${ROOT_CLASS}.autozs-ebay-seller-hub .icon-btn *,
    html.${ROOT_CLASS}.autozs-ebay-seller-hub .inline-editable-icon,
    html.${ROOT_CLASS}.autozs-ebay-seller-hub .inline-editable-icon *,
    html.${ROOT_CLASS}.autozs-ebay-seller-hub button[class*="icon" i],
    html.${ROOT_CLASS}.autozs-ebay-seller-hub button[class*="icon" i] * {
      background-color: #17201b !important;
      border-color: #2b352f !important;
      color: #edf4ef !important;
      fill: currentColor !important;
      stroke: currentColor !important;
    }
    html.${ROOT_CLASS}.autozs-ebay-seller-hub button[aria-label^="Save "][aria-label$=" to AutoZS"],
    html.${ROOT_CLASS}.autozs-ebay-seller-hub button[title^="Save "][title$=" to AutoZS"] {
      background: #17201b !important;
      background-color: #17201b !important;
      border: 1px solid #2b352f !important;
      border-radius: 6px !important;
      box-shadow: none !important;
      color: #8ed8cc !important;
      height: 28px !important;
      min-height: 28px !important;
      min-width: 32px !important;
      padding: 0 6px !important;
      width: auto !important;
    }
    html.${ROOT_CLASS}.autozs-ebay-seller-hub button[aria-label^="Save "][aria-label$=" to AutoZS"] *,
    html.${ROOT_CLASS}.autozs-ebay-seller-hub button[title^="Save "][title$=" to AutoZS"] * {
      background: transparent !important;
      background-color: transparent !important;
      color: #8ed8cc !important;
      fill: currentColor !important;
      stroke: currentColor !important;
    }
    html.${ROOT_CLASS}.autozs-ebay-seller-hub .shui-dt svg,
    html.${ROOT_CLASS}.autozs-ebay-seller-hub .shui-dt path,
    html.${ROOT_CLASS}.autozs-ebay-seller-hub .shui-dt use,
    html.${ROOT_CLASS}.autozs-ebay-seller-hub .grid-summary-bar svg,
    html.${ROOT_CLASS}.autozs-ebay-seller-hub .grid-summary-bar path {
      color: #9aa89f !important;
      fill: currentColor !important;
      stroke: currentColor !important;
    }
    html.${ROOT_CLASS}.autozs-ebay-seller-hub .shui-dt a,
    html.${ROOT_CLASS}.autozs-ebay-seller-hub .shui-dt a *,
    html.${ROOT_CLASS}.autozs-ebay-seller-hub #glbfooter a,
    html.${ROOT_CLASS}.autozs-ebay-seller-hub #glbfooter a *,
    html.${ROOT_CLASS}.autozs-ebay-seller-hub .gh-footer a,
    html.${ROOT_CLASS}.autozs-ebay-seller-hub .gh-footer a * {
      color: #8ed8cc !important;
    }
    html.${ROOT_CLASS}.autozs-ebay-seller-hub .shui-dt img,
    html.${ROOT_CLASS}.autozs-ebay-seller-hub .shui-dt picture {
      background-color: #ffffff !important;
      filter: none !important;
      opacity: 1 !important;
    }
    html.${ROOT_CLASS}.autozs-ebay-reports-uploads .title-banner,
    html.${ROOT_CLASS}.autozs-ebay-reports-uploads .app-mod-banner.multiple,
    html.${ROOT_CLASS}.autozs-ebay-reports-uploads .source-filter {
      background: #101412 !important;
      background-color: #101412 !important;
      border-color: #2b352f !important;
      box-shadow: none !important;
      color: #edf4ef !important;
    }
    html.${ROOT_CLASS}.autozs-ebay-reports-uploads .title-banner,
    html.${ROOT_CLASS}.autozs-ebay-reports-uploads .title-banner * {
      color: #edf4ef !important;
    }
    html.${ROOT_CLASS}.autozs-ebay-reports-uploads .app-mod-banner.multiple {
      gap: 16px !important;
      padding: 16px !important;
    }
    html.${ROOT_CLASS}.autozs-ebay-reports-uploads .app-mod-banner.multiple .multiple_card {
      background: #171d1a !important;
      background-color: #171d1a !important;
      border: 1px solid #2b352f !important;
      box-shadow: none !important;
      color: #edf4ef !important;
    }
    html.${ROOT_CLASS}.autozs-ebay-reports-uploads .source-filter select,
    html.${ROOT_CLASS}.autozs-ebay-reports-uploads .source-filter input,
    html.${ROOT_CLASS}.autozs-ebay-reports-uploads .source-filter button {
      background: #171d1a !important;
      background-color: #171d1a !important;
      border-color: #3a4840 !important;
      color: #edf4ef !important;
    }
    html.${ROOT_CLASS}.autozs-ebay-item-page [class*="carousel" i],
    html.${ROOT_CLASS}.autozs-ebay-item-page [class*="carousel" i] *,
    html.${ROOT_CLASS}.autozs-ebay-item-page [class*="viewport" i],
    html.${ROOT_CLASS}.autozs-ebay-item-page [class*="grid" i],
    html.${ROOT_CLASS}.autozs-ebay-item-page [class*="item-card" i],
    html.${ROOT_CLASS}.autozs-ebay-item-page [class*="item-card" i] *,
    html.${ROOT_CLASS}.autozs-ebay-item-page [class*="merch" i],
    html.${ROOT_CLASS}.autozs-ebay-item-page [class*="merch" i] *,
    html.${ROOT_CLASS}.autozs-ebay-item-page [class*="recommend" i],
    html.${ROOT_CLASS}.autozs-ebay-item-page [class*="recommend" i] * {
      border-color: #2b352f !important;
      box-shadow: none !important;
    }
    html.${ROOT_CLASS}.autozs-ebay-item-page [class*="item-card" i],
    html.${ROOT_CLASS}.autozs-ebay-item-page [class*="merch" i],
    html.${ROOT_CLASS}.autozs-ebay-item-page [class*="recommend" i],
    html.${ROOT_CLASS}.autozs-ebay-item-page [data-testid*="item" i],
    html.${ROOT_CLASS}.autozs-ebay-item-page li:has(a[href*="/itm/"]) {
      background-color: #131916 !important;
    }
    html.${ROOT_CLASS}.autozs-ebay-item-page [class*="item-card" i] a[href*="/itm/"],
    html.${ROOT_CLASS}.autozs-ebay-item-page [class*="item-card" i] a[href*="/itm/"] span,
    html.${ROOT_CLASS}.autozs-ebay-item-page [class*="item-card" i] [class*="title" i],
    html.${ROOT_CLASS}.autozs-ebay-item-page [class*="item-card" i] [class*="title" i] span,
    html.${ROOT_CLASS}.autozs-ebay-item-page [class*="merch" i] a[href*="/itm/"],
    html.${ROOT_CLASS}.autozs-ebay-item-page [class*="merch" i] a[href*="/itm/"] span,
    html.${ROOT_CLASS}.autozs-ebay-item-page [class*="merch" i] [class*="title" i],
    html.${ROOT_CLASS}.autozs-ebay-item-page [class*="merch" i] [class*="title" i] span,
    html.${ROOT_CLASS}.autozs-ebay-item-page [class*="recommend" i] a[href*="/itm/"],
    html.${ROOT_CLASS}.autozs-ebay-item-page [class*="recommend" i] a[href*="/itm/"] span,
    html.${ROOT_CLASS}.autozs-ebay-item-page [class*="recommend" i] [class*="title" i],
    html.${ROOT_CLASS}.autozs-ebay-item-page [class*="recommend" i] [class*="title" i] span,
    html.${ROOT_CLASS}.autozs-ebay-item-page li:has(a[href*="/itm/"]) a[href*="/itm/"],
    html.${ROOT_CLASS}.autozs-ebay-item-page li:has(a[href*="/itm/"]) a[href*="/itm/"] span,
    html.${ROOT_CLASS}.autozs-ebay-item-page li:has(a[href*="/itm/"]) [class*="title" i],
    html.${ROOT_CLASS}.autozs-ebay-item-page li:has(a[href*="/itm/"]) [class*="title" i] span {
      color: #edf4ef !important;
    }
    html.${ROOT_CLASS}.autozs-ebay-item-page button[aria-label*="watch" i],
    html.${ROOT_CLASS}.autozs-ebay-item-page button[aria-label*="save" i],
    html.${ROOT_CLASS}.autozs-ebay-item-page button[aria-label*="heart" i],
    html.${ROOT_CLASS}.autozs-ebay-item-page [role="button"][aria-label*="watch" i],
    html.${ROOT_CLASS}.autozs-ebay-item-page [role="button"][aria-label*="save" i],
    html.${ROOT_CLASS}.autozs-ebay-item-page button[class*="heart" i],
    html.${ROOT_CLASS}.autozs-ebay-item-page button[class*="watch" i],
    html.${ROOT_CLASS}.autozs-ebay-item-page [role="button"][class*="heart" i],
    html.${ROOT_CLASS}.autozs-ebay-item-page [role="button"][class*="watch" i] {
      background-color: #f4f7f5 !important;
      border-color: rgba(16, 20, 18, .12) !important;
      color: #17201b !important;
      opacity: 1 !important;
    }
    html.${ROOT_CLASS}.autozs-ebay-item-page button[aria-label*="watch" i] *,
    html.${ROOT_CLASS}.autozs-ebay-item-page button[aria-label*="save" i] *,
    html.${ROOT_CLASS}.autozs-ebay-item-page button[aria-label*="heart" i] *,
    html.${ROOT_CLASS}.autozs-ebay-item-page [role="button"][aria-label*="watch" i] *,
    html.${ROOT_CLASS}.autozs-ebay-item-page [role="button"][aria-label*="save" i] *,
    html.${ROOT_CLASS}.autozs-ebay-item-page button[class*="heart" i] *,
    html.${ROOT_CLASS}.autozs-ebay-item-page button[class*="watch" i] *,
    html.${ROOT_CLASS}.autozs-ebay-item-page [role="button"][class*="heart" i] *,
    html.${ROOT_CLASS}.autozs-ebay-item-page [role="button"][class*="watch" i] * {
      color: #17201b !important;
      fill: #17201b !important;
      opacity: 1 !important;
      stroke: #17201b !important;
    }
    html.${ROOT_CLASS}.autozs-ebay-item-page [class*="item-card" i] [class*="price" i],
    html.${ROOT_CLASS}.autozs-ebay-item-page [class*="item-card" i] [class*="price" i] *,
    html.${ROOT_CLASS}.autozs-ebay-item-page [class*="merch" i] [class*="price" i],
    html.${ROOT_CLASS}.autozs-ebay-item-page [class*="merch" i] [class*="price" i] *,
    html.${ROOT_CLASS}.autozs-ebay-item-page [class*="recommend" i] [class*="price" i],
    html.${ROOT_CLASS}.autozs-ebay-item-page [class*="recommend" i] [class*="price" i] *,
    html.${ROOT_CLASS}.autozs-ebay-item-page li:has(a[href*="/itm/"]) [class*="price" i],
    html.${ROOT_CLASS}.autozs-ebay-item-page li:has(a[href*="/itm/"]) [class*="price" i] *,
    html.${ROOT_CLASS}.autozs-ebay-item-page [class*="item-card" i] [class*="amount" i],
    html.${ROOT_CLASS}.autozs-ebay-item-page [class*="item-card" i] [class*="amount" i] *,
    html.${ROOT_CLASS}.autozs-ebay-item-page li:has(a[href*="/itm/"]) [aria-label^="$"],
    html.${ROOT_CLASS}.autozs-ebay-item-page li:has(a[href*="/itm/"]) [aria-label^="$"] * {
      color: #17201b !important;
      opacity: 1 !important;
    }
    html.${ROOT_CLASS}.autozs-ebay-item-page [class*="item-card" i] [class*="price" i]:not(.s-item__price),
    html.${ROOT_CLASS}.autozs-ebay-item-page [class*="merch" i] [class*="price" i]:not(.s-item__price),
    html.${ROOT_CLASS}.autozs-ebay-item-page [class*="recommend" i] [class*="price" i]:not(.s-item__price),
    html.${ROOT_CLASS}.autozs-ebay-item-page li:has(a[href*="/itm/"]) [class*="price" i]:not(.s-item__price),
    html.${ROOT_CLASS}.autozs-ebay-item-page li:has(a[href*="/itm/"]) [aria-label^="$"] {
      background-color: #f4f7f5 !important;
      border-color: rgba(16, 20, 18, .12) !important;
    }
    html.${ROOT_CLASS}.autozs-ebay-item-page .autozs-ebay-price-pill {
      background-color: #f4f7f5 !important;
      border-color: rgba(16, 20, 18, .12) !important;
      color: #17201b !important;
      opacity: 1 !important;
    }
    html.${ROOT_CLASS}.autozs-ebay-item-page .autozs-ebay-price-pill *,
    html.${ROOT_CLASS}.autozs-ebay-item-page .autozs-ebay-price-text,
    html.${ROOT_CLASS}.autozs-ebay-item-page .autozs-ebay-price-text * {
      color: #17201b !important;
      fill: #17201b !important;
      stroke: #17201b !important;
    }
    html.${ROOT_CLASS}.autozs-ebay-item-page [class*="media-scrim" i] > [class*="opacity-5" i] {
      opacity: .05 !important;
    }
    html.${ROOT_CLASS}.autozs-ebay-item-page [class*="media-scrim" i] > [class*="hover:opacity-10" i]:hover {
      opacity: .1 !important;
    }
    html.${ROOT_CLASS}.autozs-ebay-item-page body,
    html.${ROOT_CLASS}.autozs-ebay-item-page main,
    html.${ROOT_CLASS}.autozs-ebay-item-page #mainContent,
    html.${ROOT_CLASS}.autozs-ebay-item-page #CenterPanel,
    html.${ROOT_CLASS}.autozs-ebay-item-page #RightPanel,
    html.${ROOT_CLASS}.autozs-ebay-item-page #RightSummaryPanel,
    html.${ROOT_CLASS}.autozs-ebay-item-page .center-panel-container,
    html.${ROOT_CLASS}.autozs-ebay-item-page .right-summary-panel-container,
    html.${ROOT_CLASS}.autozs-ebay-item-page .main-container,
    html.${ROOT_CLASS}.autozs-ebay-item-page .x-vi-evo-main-container,
    html.${ROOT_CLASS}.autozs-ebay-item-page .d-vi-evo-region,
    html.${ROOT_CLASS}.autozs-ebay-item-page .x-evo-atf-left-river,
    html.${ROOT_CLASS}.autozs-ebay-item-page .x-evo-atf-right-river,
    html.${ROOT_CLASS}.autozs-ebay-item-page .x-sellercard-atf_main,
    html.${ROOT_CLASS}.autozs-ebay-item-page .x-sellercard-atf__education,
    html.${ROOT_CLASS}.autozs-ebay-item-page .ux-education {
      background: #101412 !important;
      background-color: #101412 !important;
    }
    html.${ROOT_CLASS}.autozs-ebay-item-page .x-pda-placements--102303 #placement_102303 > div {
      background: #101412 !important;
      border-color: #2b352f !important;
      box-shadow: none !important;
      color: #edf4ef !important;
    }
    html.${ROOT_CLASS}.autozs-ebay-item-page .x-pda-placements--102303 #placement_102303 div,
    html.${ROOT_CLASS}.autozs-ebay-item-page .x-pda-placements--102303 #placement_102303 span {
      color: #edf4ef !important;
    }
    html.${ROOT_CLASS}.autozs-ebay-item-page .x-pda-placements--102303 #placement_102303 a,
    html.${ROOT_CLASS}.autozs-ebay-item-page .x-pda-placements--102303 #placement_102303 a span,
    html.${ROOT_CLASS}.autozs-ebay-item-page .x-pda-placements--102303 #placement_102303 a div {
      color: #8ed8cc !important;
    }
    html.${ROOT_CLASS}.autozs-ebay-item-page .x-pda-placements--102303 #placement_102303 button {
      background: #25312b !important;
      border-color: #36453d !important;
      color: #edf4ef !important;
    }
    html.${ROOT_CLASS}.autozs-ebay-item-page .x-pda-placements--102303 #placement_102303 img {
      filter: none !important;
      opacity: 1 !important;
    }
    html.${ROOT_CLASS}.autozs-ebay-item-page .x-pda-placements--102303 #placement_102303 [class*="sponsored" i],
    html.${ROOT_CLASS}.autozs-ebay-item-page .x-pda-placements--102303 #placement_102303 [class*="ad-label" i] {
      color: #aab6af !important;
    }
    html.${ROOT_CLASS}.autozs-ebay-item-page .x-sellercard-atf__education,
    html.${ROOT_CLASS}.autozs-ebay-item-page .x-sellercard-atf__education *,
    html.${ROOT_CLASS}.autozs-ebay-item-page .ux-education,
    html.${ROOT_CLASS}.autozs-ebay-item-page .ux-education__content,
    html.${ROOT_CLASS}.autozs-ebay-item-page .ux-education__title,
    html.${ROOT_CLASS}.autozs-ebay-item-page .ux-education__subtitle,
    html.${ROOT_CLASS}.autozs-ebay-item-page .ux-education__icon,
    html.${ROOT_CLASS}.autozs-ebay-item-page .vim.x-shop-with-confidence,
    html.${ROOT_CLASS}.autozs-ebay-item-page .tabs__content,
    html.${ROOT_CLASS}.autozs-ebay-item-page #seo-footer-container,
    html.${ROOT_CLASS}.autozs-ebay-item-page .seo-footer-container {
      background: #101412 !important;
      background-color: #101412 !important;
      border-color: #2b352f !important;
      color: #edf4ef !important;
    }
    html.${ROOT_CLASS}.autozs-ebay-item-page .x-sellercard-atf__education a,
    html.${ROOT_CLASS}.autozs-ebay-item-page .x-sellercard-atf__education a span,
    html.${ROOT_CLASS}.autozs-ebay-item-page .ux-education a,
    html.${ROOT_CLASS}.autozs-ebay-item-page .ux-education a span,
    html.${ROOT_CLASS}.autozs-ebay-item-page .vim.x-shop-with-confidence a,
    html.${ROOT_CLASS}.autozs-ebay-item-page .vim.x-shop-with-confidence a span,
    html.${ROOT_CLASS}.autozs-ebay-item-page .tabs__content a,
    html.${ROOT_CLASS}.autozs-ebay-item-page .tabs__content a span,
    html.${ROOT_CLASS}.autozs-ebay-item-page #seo-footer-container a,
    html.${ROOT_CLASS}.autozs-ebay-item-page #seo-footer-container a span,
    html.${ROOT_CLASS}.autozs-ebay-item-page .seo-footer-container a,
    html.${ROOT_CLASS}.autozs-ebay-item-page .seo-footer-container a span {
      color: #8ed8cc !important;
    }
    html.${ROOT_CLASS}.autozs-ebay-item-page .x-sellercard-atf__education svg,
    html.${ROOT_CLASS}.autozs-ebay-item-page .x-sellercard-atf__education path,
    html.${ROOT_CLASS}.autozs-ebay-item-page .ux-education svg,
    html.${ROOT_CLASS}.autozs-ebay-item-page .ux-education path {
      color: #8ed8cc !important;
      fill: currentColor !important;
      stroke: currentColor !important;
    }
  `;

  function injectStyle() {
    const existing = document.getElementById(STYLE_ID);
    if (existing?.getAttribute?.("data-autozs-build") === DARK_MODE_BUILD) return;
    if (existing) existing.remove();
    const style = document.createElement("style");
    style.id = STYLE_ID;
    style.setAttribute("data-autozs-build", DARK_MODE_BUILD);
    style.textContent = css;
    (document.head || document.documentElement).appendChild(style);
  }

  function setEnabled(enabled) {
    injectStyle();
    document.documentElement.classList.toggle(ROOT_CLASS, Boolean(enabled));
    document.documentElement.classList.toggle("autozs-ebay-item-page", /^\/itm\//i.test(location.pathname || ""));
    document.documentElement.classList.toggle(
      "autozs-ebay-listing-editor",
      /^\/(?:lstng|sl\/(?:list|prelist))(?:\/|$)/i.test(location.pathname || ""),
    );
    document.documentElement.classList.toggle("autozs-ebay-prelist", /^\/sl\/prelist(?:\/|$)/i.test(location.pathname || ""));
    document.documentElement.classList.toggle("autozs-ebay-seller-hub", /^\/sh\//i.test(location.pathname || ""));
    document.documentElement.classList.toggle(
      "autozs-ebay-reports-uploads",
      /^\/sh\/reports\/uploads\/?$/i.test(location.pathname || ""),
    );
    if (enabled) {
      markItemPageRecommendationPrices();
      cleanHiddenEbayOverlays();
    }
  }

  function localFallbackTheme() {
    return window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
  }

  async function readDarkModeTheme() {
    if (typeof readAppTheme === "function") return readAppTheme();
    try {
      const response = await fetch(`${LOCAL_API}/settings`, { cache: "no-store" });
      if (!response.ok) throw new Error(`settings returned ${response.status}`);
      const settings = await response.json();
      return settings.ui_theme === "dark" || settings.ui_theme === "light" ? settings.ui_theme : localFallbackTheme();
    } catch {
      return localFallbackTheme();
    }
  }

  function cleanHiddenEbayOverlays() {
    if (!document.documentElement.classList.contains(ROOT_CLASS)) return;
    document.querySelectorAll(".lightbox-dialog--hide, .lightbox-dialog[aria-hidden='true'], .ux-overlay[aria-hidden='true']").forEach((element) => {
      element.style.setProperty("display", "none", "important");
      element.style.setProperty("opacity", "0", "important");
      element.style.setProperty("pointer-events", "none", "important");
      element.style.setProperty("visibility", "hidden", "important");
    });
  }

  function recommendationCardRoots() {
    if (!/^\/itm\//i.test(location.pathname || "")) return [];
    const selectors = [
      '[class*="item-card" i]',
      '[class*="merch" i]',
      '[class*="recommend" i]',
      '[data-testid*="item" i]',
      'li:has(a[href*="/itm/"])',
    ];
    try {
      return Array.from(document.querySelectorAll(selectors.join(",")));
    } catch {
      return [];
    }
  }

  function markItemPageRecommendationPrices() {
    const pricePattern = /^\s*\$[\d,.]+(?:\s*\$[\d,.]+)?\s*$/;
    recommendationCardRoots().forEach((root) => {
      root.querySelectorAll(".autozs-ebay-price-pill, .autozs-ebay-price-text").forEach((element) => {
        if (element.querySelector("img,picture,video,canvas")) {
          element.classList.remove("autozs-ebay-price-pill", "autozs-ebay-price-text");
        }
      });
      root.querySelectorAll("span, div, strong, b").forEach((element) => {
        const text = String(element.textContent || "").replace(/\s+/g, " ").trim();
        if (!pricePattern.test(text)) return;
        if (text.length > 32) return;
        if (element.querySelector("img,picture,video,canvas")) return;
        element.classList.add("autozs-ebay-price-text");
        let pill = element;
        for (let depth = 0; depth < 4 && pill?.parentElement && pill.parentElement !== root; depth += 1) {
          const parentText = String(pill.parentElement.textContent || "").replace(/\s+/g, " ").trim();
          if (parentText.length <= 48 && parentText.includes("$") && !pill.parentElement.querySelector("img,picture,video,canvas")) {
            pill = pill.parentElement;
          }
        }
        if (pill && pill !== root && !pill.querySelector("img,picture,video,canvas")) {
          pill.classList.add("autozs-ebay-price-pill");
        }
      });
    });
  }

  let priceMarkerScheduled = false;

  function schedulePriceMarker() {
    if (priceMarkerScheduled) return;
    priceMarkerScheduled = true;
    setTimeout(() => {
      priceMarkerScheduled = false;
      if (document.documentElement.classList.contains(ROOT_CLASS)) {
        markItemPageRecommendationPrices();
        cleanHiddenEbayOverlays();
      }
    }, 250);
  }

  function startPriceMarkerObserver() {
    if (!document.body) {
      setTimeout(startPriceMarkerObserver, 250);
      return;
    }
    new MutationObserver(schedulePriceMarker).observe(document.body, { childList: true, subtree: true });
    schedulePriceMarker();
  }

  async function syncEbayDarkMode() {
    const theme = await readDarkModeTheme();
    setEnabled(theme === "dark");
  }

  setEnabled(false);
  syncEbayDarkMode().catch(() => setEnabled(localFallbackTheme() === "dark"));
  [1500, 5000].forEach((delay) => setTimeout(() => syncEbayDarkMode().catch(() => {}), delay));
  window.addEventListener("pageshow", () => syncEbayDarkMode().catch(() => {}));
  document.addEventListener("visibilitychange", () => {
    if (!document.hidden) syncEbayDarkMode().catch(() => {});
  });
  window.matchMedia?.("(prefers-color-scheme: dark)")?.addEventListener?.("change", () => {
    syncEbayDarkMode().catch(() => {});
  });
  startPriceMarkerObserver();
})();
