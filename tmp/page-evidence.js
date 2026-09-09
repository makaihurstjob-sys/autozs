({url:location.href,text:document.body.innerText,buttons:[...document.querySelectorAll("button")].map(b=>({text:b.innerText,label:b.getAttribute("aria-label")}))})
