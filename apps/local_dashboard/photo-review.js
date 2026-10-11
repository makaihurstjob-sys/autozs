window.readDepopPhotoReadiness = async function(api, data) {
          const [products, jobs] = await Promise.all([api("/depop/photo-queue"), api("/depop/jobs?limit=1000")]);
          if (jobs.length >= 1000) throw new Error("Queue history exceeds counter limit");
          const reviews = [];
          // Bound concurrency so a large catalog does not overwhelm the API.
          for (let index = 0; index < products.length; index += 6) {
            reviews.push(...await Promise.all(products.slice(index, index + 6).map(item =>
              data && item.product_id === data.product_id ? Promise.resolve(data) : api(`/depop/photo-review/${item.product_id}`))));
          }
          if (data && !reviews.some(r => r.product_id === data.product_id)) reviews.push(data);
          return { reviews, jobs };

};
window.countDepopPhotoReadiness = function({reviews, jobs}, productId, selectedVariantId) {
        let ready = 0;
        let progress = "";
        for (const review of reviews) for (const base of review.variants.filter(v => !v.variant_key.includes("::batch-"))) {
          const count = review.photos.filter(p => p.status === "approved" && p.variant_id === base.id).length;
          for (let index = 1; index <= Math.floor(count / 4); index++) {
            const variant = index === 1 ? base : review.variants.find(v => v.variant_key === `${base.variant_key}::batch-${index}`);
            const used = variant && (variant.depop_listing_id || jobs.some(j => j.variant_id === variant.id && (j.status !== "cancelled" || j.attempts > 0)));
            if (!used) ready++;
          }
          if (review.product_id === productId && base.id === selectedVariantId) progress = `${base.color || base.variant_key}: ${count % 4}/4 next set`;
        }

 return {ready, progress};
};
// Shared photo review controller. Queries and dialogs stay within its mount.
window.mountPhotoReview = function(root, options = {}) {
  const lifetime = new AbortController();
  const nativeDocument = globalThis.document;
  const nativeWindow = globalThis.window;
  const document = {
    getElementById: id => root.querySelector(`[id="${id}"]`),
    querySelector: selector => root.querySelector(selector),
    querySelectorAll: selector => root.querySelectorAll(selector),
    createElement: tag => nativeDocument.createElement(tag),
    createComment: text => nativeDocument.createComment(text),
    body: root, documentElement: nativeDocument.documentElement,
  };
  const window = {
    innerWidth: nativeWindow.innerWidth,
    addEventListener: (type, handler) => nativeWindow.addEventListener(type, handler, {signal:lifetime.signal}),
    removeEventListener: (type, handler) => nativeWindow.removeEventListener(type, handler),
  };

      const API_STORAGE_KEY = "ebayAutomationApiBaseUrl";
      const params = options.params || new URLSearchParams(location.search);
      const embedded = params.get("embedded") === "1";
      if (embedded && !options.native) document.documentElement.dataset.embedded = "true";
      document.getElementById("review-products").href = "photos.html?" + (embedded ? "embedded=1&" : "") + "api=" + encodeURIComponent(params.get("api") || "");
      if (embedded) document.getElementById("back-to-products").href = "photos.html?embedded=1" +
        (params.get("api") ? `&api=${encodeURIComponent(params.get("api"))}` : "");
      const normalizeApiBaseUrl = (value) => String(value || "").trim().replace(/\/+$/, "");
      function defaultApiBaseUrl() {
        if (["localhost", "127.0.0.1", ""].includes(location.hostname)) {
          return `http://${location.hostname || "127.0.0.1"}:8000`;
        }
        return "";
      }
      const API = normalizeApiBaseUrl(
        params.get("api") || localStorage.getItem(API_STORAGE_KEY) || defaultApiBaseUrl()
      );
      const productId = Number(params.get("product_id") || 0);

      const deck = document.getElementById("deck");
      const chipsEl = document.getElementById("variants");
      const counterEl = document.getElementById("counter");
      const hintEl = document.getElementById("hint");
      const emptyEl = document.getElementById("empty");
      const undoBtn = document.getElementById("undo");

      let queue = [];
      let variants = [];
      let readinessData = null;
      let readinessGeneration = 0;
      let readinessController;
      let selectedVariantId = null;
      let total = 0;
      let done = 0;
      let history = [];
      let busy = false;
      let cropMode = false;
      const cropStates = new Map();

      const api = async (path, options) => {
        const response = await fetch(API + path, { ...options, signal: options?.signal || lifetime.signal });
        if (!response.ok) throw new Error((await response.text()).slice(0, 200));
        return response.json();
      };

      async function loadPicker() {
        const queue = await api("/depop/photo-queue");
        void refreshReadiness();
        document.getElementById("product-title").textContent = "Photo review";
        document.getElementById("product-sub").textContent = queue.length
          ? `${queue.filter((item) => item.pending).length} product(s) waiting`
          : "Nothing captured yet";
        counterEl.style.display = "none";
        for (const selector of [".crop-toolbar", "#crop-controls", "#all-colors", "#review-products", "#hint"]) document.querySelector(selector).style.display = "none";
        undoBtn.style.display = "none";
        deck.style.display = "none";
        chipsEl.style.display = "none";
        document.querySelector(".actions").style.display = "none";
        const picker = document.getElementById("picker");
        picker.style.display = "block";
        document.querySelector("main").style.justifyContent = "flex-start";
        if (!queue.length) {
          picker.innerHTML =
            '<p style="text-align:center;color:var(--muted)">Import an Amazon listing to queue up its variations and review photos.</p>';
          return;
        }
        picker.innerHTML = "";
        for (const item of queue) {
          const row = document.createElement("a");
          row.className = "queue-row";
          const rowUrl = new URL("photos.html", location.href);
          rowUrl.searchParams.set("product_id", item.product_id);
          if (params.get("api")) rowUrl.searchParams.set("api", params.get("api"));
          if (embedded) rowUrl.searchParams.set("embedded", "1");
          row.href = rowUrl.href;
          if (options.navigate) row.addEventListener("click", event => { event.preventDefault(); options.navigate(item.product_id); });
          const img = document.createElement("img");
          img.src = amazonSized(item.cover_image, 120);
          img.alt = "";
          const text = document.createElement("div");
          text.className = "t";
          const name = document.createElement("b");
          name.textContent = item.product_title;
          const sub = document.createElement("span");
          sub.textContent = `${item.variants} variation(s) - ${item.approved} approved, ${item.rejected} rejected`;
          text.append(name, sub);
          const badge = document.createElement("span");
          badge.className = `badge ${item.pending ? "todo" : "done"}`;
          badge.textContent = item.pending ? `${item.pending} to review` : "done";
          row.append(img, text, badge);
          picker.append(row);
        }
      }

      async function load() {
        if (!productId) {
          await loadPicker();
          return;
        }
        const data = await api(`/depop/photo-review/${productId}`);
        variants = data.variants;
        // Render the current product without waiting for catalog-wide readiness.
        void refreshReadiness(data);
        allVariationPhotos = data.photos.filter((p) => p.kind === "variation");
        // Variation photos already know their colour, so only the unattributed
        // review photos need a human decision.
        const reviewPhotos = data.photos.filter((p) => p.kind === "review");
        queue = reviewPhotos.filter((p) => p.status === "pending");
        done = reviewPhotos.length - queue.length;
        total = reviewPhotos.length;
        document.getElementById("product-title").textContent = (data.product_title || `Product ${productId}`).slice(0, 64);
        document.getElementById("product-sub").textContent =
          `${variants.length} variation(s) - swipe review photos onto a colour`;
        renderChips();
        render();
      }

      async function refreshReadiness(data) {
        const el = document.getElementById("photo-readiness");
        el.hidden = false;
        const generation = ++readinessGeneration;
        readinessController?.abort();
        const controller = readinessController = new AbortController();
        const cancel = () => controller.abort();
        lifetime.signal.addEventListener("abort", cancel, {once:true});
        el.textContent = "Updating approved count...";
        try {
          const updated = await globalThis.readDepopPhotoReadiness(path => api(path, {signal:controller.signal}), data);
          if (lifetime.signal.aborted || generation !== readinessGeneration) return;
          readinessData = updated;
          renderReadiness();
          globalThis.dispatchEvent(new CustomEvent("depop-readiness", {detail: globalThis.countDepopPhotoReadiness(readinessData).ready}));
        } catch (error) {
          if (lifetime.signal.aborted || generation !== readinessGeneration) return;
          readinessData = null;
          el.textContent = "Photo-ready count unavailable";
        } finally {
          lifetime.signal.removeEventListener("abort", cancel);
        }
      }

      function renderReadiness() {
        if (!readinessData) return;
        const { reviews, jobs } = readinessData;
        const {ready, progress} = globalThis.countDepopPhotoReadiness(readinessData, productId, selectedVariantId);
        document.getElementById("photo-readiness").textContent = `${ready} photo-ready listing${ready === 1 ? "" : "s"} | All Depop products` +
          (progress ? ` | ${progress}` : "");
        document.getElementById("photo-readiness").title = "Four approved photos of the same color per listing. Downloads and listing checks still apply.";
      }

      /** Amazon renders any stored size on demand, so ask for a crisp chip-sized
       *  copy instead of scaling a 40px thumbnail up or a 1500px original down. */
      function amazonSized(url, size) {
        return String(url || "").replace(/(\/images\/I\/[^./]+)(\._[^.]+_)?\.(jpg|jpeg|png)$/i, `$1._SS${size}_.$3`);
      }

      function variantImage(variant) {
        const match = allVariationPhotos.find((p) => p.variant_id === variant.id);
        return match ? amazonSized(match.image_url, 200) : "";
      }

      let allVariationPhotos = [];

      function renderChips() {
        renderReadiness();
        chipsEl.innerHTML = "";
        variants.forEach((variant, index) => {
          const chip = document.createElement("button");
          chip.className = "chip" + (variant.id === selectedVariantId ? " selected" : "");
          chip.title = `${variant.color} (press ${index + 1})`;
          const img = document.createElement("img");
          img.src = variantImage(variant);
          img.alt = variant.color;
          const label = document.createElement("span");
          label.textContent = variant.color || variant.variant_key;
          chip.append(img, label);
          chip.addEventListener("click", () => {
            selectedVariantId = variant.id;
            renderChips();
            updateHint();
          });
          chipsEl.append(chip);
        });
      }

      function updateHint() {
        if (!queue.length) return;
        if (cropMode) {
          hintEl.textContent = "Drag to reposition. Pinch or use the slider to zoom, then tap Done.";
          return;
        }
        const variant = variants.find((v) => v.id === selectedVariantId);
        if (!variant) {
          hintEl.textContent = "Pick a variation below, then swipe right to approve";
          return;
        }
        const suggested = queue[0] && queue[0].variant_id === variant.id;
        hintEl.textContent = suggested
          ? `Matched to "${variant.color}" from the reviewer's order - swipe right to confirm`
          : `Swipe right to approve into "${variant.color}"`;
      }

      function render() {
        document.getElementById("all-colors").hidden = !queue.length;
        deck.innerHTML = "";
        counterEl.textContent = total ? `${done} / ${total} reviewed` : "no review photos";
        undoBtn.disabled = !history.length;
        if (!queue.length) {
          emptyEl.style.display = "block";
          document.querySelector(".actions").style.display = "none";
          chipsEl.style.display = "none";
          hintEl.textContent = "";
          document.getElementById("empty-detail").textContent = total
            ? `${total} review photo(s) decided.`
            : "This product has no customer review photos.";
          return;
        }
        emptyEl.style.display = "none";
        document.querySelector(".actions").style.display = "flex";
        chipsEl.style.display = "flex";
        const next = queue[1];
        const currentCard = makeCard(queue[0], false);
        if (next) deck.append(makeCard(next, true));
        deck.append(currentCard);
        const currentMode = cropState(queue[0]).mode;
        document.getElementById("square-crop").setAttribute("aria-pressed", String(currentMode === "crop"));
        document.getElementById("expand-toggle").classList.toggle("active", currentMode === "blur");
        document.getElementById("expand-toggle").textContent = currentMode === "blur" ? "Use square crop" : "Expand background";
        // A pending photo that already carries a variant was matched through its
        // review id; pre-select it so the swipe is a confirmation, not a lookup.
        selectedVariantId = queue[0].variant_id || null;
        renderChips();
        updateHint();
      }

      function makeCard(photo, behind) {
        const card = document.createElement("div");
        card.className = "card" + (behind ? " behind" : "");
        const backdrop = document.createElement("img");
        backdrop.className = "blur-backdrop";
        backdrop.src = photo.image_url;
        backdrop.alt = "";
        const img = document.createElement("img");
        img.className = "photo";
        img.fetchPriority = behind ? "low" : "high";
        img.decoding = "async";
        img.src = photo.image_url;
        img.alt = "";
        img.loading = "eager";
        img.draggable = false;
        img.addEventListener("error", () => {
          img.src = photo.thumb_url || "";
        });
        img.addEventListener("load", () => applyCrop(img, photo));
        const meta = document.createElement("div");
        meta.className = "meta";
        const tag = document.createElement("span");
        tag.className = `tag ${photo.kind}`;
        tag.textContent = photo.kind;
        const text = document.createElement("span");
        text.textContent = photo.width && photo.height ? `${photo.width}x${photo.height}` : "customer photo";
        meta.append(tag, text);
        const yes = document.createElement("div");
        yes.className = "stamp yes";
        yes.textContent = "KEEP";
        const no = document.createElement("div");
        no.className = "stamp no";
        no.textContent = "NOPE";
        card.append(backdrop, img, meta, yes, no);
        if (!behind) {
          attachDrag(card);
          attachCropGestures(img, photo);
        }
        return card;
      }

      function cropState(photo) {
        if (!cropStates.has(photo.id)) cropStates.set(photo.id, {
          x: Number(photo.crop_x || 0), y: Number(photo.crop_y || 0), zoom: Number(photo.crop_zoom || 1),
          mode: photo.background_mode === "blur" ? "blur" : "crop",
        });
        return cropStates.get(photo.id);
      }

      function cropGeometry(img, state) {
        const box = deck.getBoundingClientRect();
        const ratio = Math.max(box.width / (img.naturalWidth || 1), box.height / (img.naturalHeight || 1));
        const width = (img.naturalWidth || 1) * ratio;
        const height = (img.naturalHeight || 1) * ratio;
        return { width, height, maxX: Math.max(0, (width * state.zoom - box.width) / 2), maxY: Math.max(0, (height * state.zoom - box.height) / 2) };
      }

      function applyCrop(img, photo) {
        if (!img.naturalWidth) return;
        const state = cropState(photo);
        const backdrop = img.parentElement?.querySelector(".blur-backdrop");
        if (state.mode === "blur") {
          img.classList.add("expand");
          if (backdrop) backdrop.style.display = "block";
          img.style.width = "100%";
          img.style.height = "100%";
          img.style.transform = "translate(-50%, -50%)";
          document.getElementById("crop-zoom").value = 1;
          return;
        }
        img.classList.remove("expand");
        if (backdrop) backdrop.style.display = "none";
        const geometry = cropGeometry(img, state);
        img.style.width = `${geometry.width}px`;
        img.style.height = `${geometry.height}px`;
        img.style.transform = `translate(-50%, -50%) translate(${state.x * geometry.maxX}px, ${state.y * geometry.maxY}px) scale(${state.zoom})`;
        document.getElementById("crop-zoom").value = state.zoom;
      }

      function attachCropGestures(img, photo) {
        let pointers = new Map();
        let start = null;
        const begin = (event) => {
          if (!cropMode) return;
          if (cropState(photo).mode === "blur") return;
          event.preventDefault();
          try { img.setPointerCapture?.(event.pointerId); } catch {}
          pointers.set(event.pointerId, { x: event.clientX, y: event.clientY });
          const state = cropState(photo);
          start = { x: state.x, y: state.y, zoom: state.zoom, points: [...pointers.values()] };
          img.classList.add("adjusting");
        };
        const move = (event) => {
          if (!cropMode || !pointers.has(event.pointerId)) return;
          event.preventDefault();
          pointers.set(event.pointerId, { x: event.clientX, y: event.clientY });
          const points = [...pointers.values()];
          const state = cropState(photo);
          if (points.length > 1 && start?.points.length > 1) {
            const distance = Math.hypot(points[0].x - points[1].x, points[0].y - points[1].y);
            const initial = Math.hypot(start.points[0].x - start.points[1].x, start.points[0].y - start.points[1].y) || 1;
            state.zoom = Math.max(1, Math.min(4, start.zoom * distance / initial));
          } else if (points.length === 1 && start) {
            const geometry = cropGeometry(img, state);
            state.x = geometry.maxX ? Math.max(-1, Math.min(1, start.x + (points[0].x - start.points[0].x) / geometry.maxX)) : 0;
            state.y = geometry.maxY ? Math.max(-1, Math.min(1, start.y + (points[0].y - start.points[0].y) / geometry.maxY)) : 0;
          }
          applyCrop(img, photo);
        };
        const end = (event) => { pointers.delete(event.pointerId); start = null; img.classList.remove("adjusting"); };
        img.addEventListener("pointerdown", begin);
        img.addEventListener("pointermove", move);
        img.addEventListener("pointerup", end);
        img.addEventListener("pointercancel", end);
        img.addEventListener("wheel", (event) => {
          if (!cropMode) return;
          if (cropState(photo).mode === "blur") return;
          event.preventDefault();
          const state = cropState(photo);
          state.zoom = Math.max(1, Math.min(4, state.zoom - event.deltaY * 0.002));
          applyCrop(img, photo);
        }, { passive: false });
      }

      function attachDrag(card) {
        let startX = 0;
        let startY = 0;
        let dx = 0;
        let dragging = false;
        const yes = card.querySelector(".stamp.yes");
        const no = card.querySelector(".stamp.no");

        const down = (event) => {
          if (busy || cropMode) return;
          dragging = true;
          card.classList.remove("animate");
          const point = event.touches ? event.touches[0] : event;
          startX = point.clientX;
          startY = point.clientY;
        };
        const move = (event) => {
          if (!dragging) return;
          const point = event.touches ? event.touches[0] : event;
          dx = point.clientX - startX;
          const dy = point.clientY - startY;
          card.style.transform = `translate(${dx}px, ${dy * 0.25}px) rotate(${dx / 22}deg)`;
          yes.style.opacity = dx > 0 ? Math.min(1, dx / 110) : 0;
          no.style.opacity = dx < 0 ? Math.min(1, -dx / 110) : 0;
          if (event.cancelable) event.preventDefault();
        };
        const up = () => {
          if (!dragging) return;
          dragging = false;
          if (Math.abs(dx) > 95) {
            decide(dx > 0 ? "approved" : "rejected");
          } else {
            card.classList.add("animate");
            card.style.transform = "";
            yes.style.opacity = 0;
            no.style.opacity = 0;
          }
          dx = 0;
        };

        card.addEventListener("mousedown", down);
        window.addEventListener("mousemove", move);
        window.addEventListener("mouseup", up);
        card.addEventListener("touchstart", down, { passive: true });
        card.addEventListener("touchmove", move, { passive: false });
        card.addEventListener("touchend", up);
      }

      function flyOut(direction) {
        const card = deck.lastElementChild;
        if (!card) return;
        card.classList.add("animate");
        card.style.transform = `translate(${direction * window.innerWidth}px, 0) rotate(${direction * 28}deg)`;
        card.style.opacity = "0";
      }

      async function decide(status) {
        if (busy || !queue.length || cropDialog.open || colorDialog.open) return;
        if (status === "approved" && !selectedVariantId) {
          // Approving is also an assignment, so refuse until a colour is chosen.
          chipsEl.classList.remove("nudge");
          void chipsEl.offsetWidth;
          chipsEl.classList.add("nudge");
          hintEl.textContent = "Pick which variation this photo belongs to first.";
          const card = deck.lastElementChild;
          if (card) {
            card.classList.add("animate");
            card.style.transform = "";
            card.querySelectorAll(".stamp").forEach((s) => (s.style.opacity = 0));
          }
          return;
        }
        busy = true;
        const photo = queue[0];
        const crop = cropState(photo);
        const variantId = status === "approved" ? selectedVariantId : null;
        flyOut(status === "approved" ? 1 : -1);
        try {
          await api(`/depop/source-photos/${photo.id}/decision`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              status, variant_id: variantId,
              crop_x: crop.x, crop_y: crop.y, crop_zoom: crop.zoom,
              background_mode: crop.mode,
            }),
          });
          history.push({ photo, status, variantId, crop: { ...crop } });
          queue.shift();
          done += 1;
          void refreshReadiness();
        } catch (error) {
          hintEl.textContent = `Could not save: ${error.message}`;
        } finally {
          setTimeout(() => {
            busy = false;
            render();
          }, 240);
        }
      }

      async function undo() {
        if (busy || cropDialog.open || colorDialog.open) return;
        const last = history.pop();
        if (!last) return;
        busy = true;
        try {
          await api(`/depop/source-photos/${last.photo.id}/decision`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              status: "pending", variant_id: null,
              crop_x: last.crop?.x || 0, crop_y: last.crop?.y || 0, crop_zoom: last.crop?.zoom || 1,
              background_mode: last.crop?.mode || "crop",
            }),
          });
          queue.unshift(last.photo);
          done = Math.max(0, done - 1);
          void refreshReadiness();
        } catch (error) {
          history.push(last);
          hintEl.textContent = `Undo failed: ${error.message}`;
        } finally {
          busy = false;
          render();
        }
      }

      document.getElementById("square-crop").addEventListener("click", () => {
        if (!queue.length) return;
        cropState(queue[0]).mode = "crop";
        document.getElementById("square-crop").setAttribute("aria-pressed", "true");
        const img = deck.lastElementChild?.querySelector("img.photo");
        if (img) applyCrop(img, queue[0]);
        hintEl.textContent = "1:1 square crop. Adjust crop to position and zoom.";
      });
      new ResizeObserver(() => {
        const img = deck.lastElementChild?.querySelector("img.photo");
        if (img && queue.length) applyCrop(img, queue[0]);
      }).observe(deck);
      document.getElementById("btn-yes").addEventListener("click", () => decide("approved"));
      document.getElementById("btn-no").addEventListener("click", () => decide("rejected"));
      const cropDialog = document.createElement("dialog");
      cropDialog.className = "crop-dialog";
      cropDialog.innerHTML = '<h2>Adjust crop</h2><div class="crop-surface"></div><p>Drag to reposition ? Pinch to zoom</p><div class="crop-sliders"></div><button id="crop-reset">Reset</button><div class="crop-dialog-actions"><button id="crop-cancel">Cancel</button><button id="crop-save">Save crop</button></div>';
      document.body.append(cropDialog);
      let cropSnapshot, deckAnchor, sliderAnchor;
      function closeCrop(save) {
        if (!cropDialog.open) return;
        if (!save && queue.length) Object.assign(cropState(queue[0]), cropSnapshot);
        deckAnchor.replaceWith(deck); sliderAnchor.replaceWith(document.getElementById("crop-controls"));
        cropMode = false;
        document.getElementById("crop-controls").classList.remove("visible");
        cropDialog.close();
        const img = deck.lastElementChild?.querySelector("img.photo");
        if (img && queue.length) applyCrop(img, queue[0]);
        updateHint();
      }
      document.getElementById("crop-toggle").addEventListener("click", () => {
        if (!queue.length) return;
        cropSnapshot = { ...cropState(queue[0]) };
        cropState(queue[0]).mode = "crop";
        cropMode = true;
        deckAnchor = document.createComment("deck"); deck.replaceWith(deckAnchor);
        const sliders = document.getElementById("crop-controls");
        sliderAnchor = document.createComment("sliders"); sliders.replaceWith(sliderAnchor);
        cropDialog.querySelector(".crop-surface").append(deck);
        cropDialog.querySelector(".crop-sliders").append(sliders);
        sliders.classList.add("visible");
        cropDialog.showModal();
        const img = deck.lastElementChild?.querySelector("img.photo"); if (img) applyCrop(img, queue[0]);
      });
      cropDialog.querySelector("#crop-save").onclick = () => closeCrop(true);
      cropDialog.querySelector("#crop-cancel").onclick = () => closeCrop(false);
      cropDialog.addEventListener("cancel", event => { event.preventDefault(); closeCrop(false); });
      cropDialog.querySelector("#crop-reset").onclick = () => {
        Object.assign(cropState(queue[0]), { x:0, y:0, zoom:1, mode:"crop" });
        const img = deck.lastElementChild?.querySelector("img.photo"); if (img) applyCrop(img, queue[0]);
      };
      const colorDialog = document.createElement("dialog");
      colorDialog.className = "color-dialog";
      colorDialog.innerHTML = '<h2>Assign a color</h2><input id="color-search" type="search" placeholder="Search colors" aria-label="Search colors"><div class="color-grid"></div><button id="color-done">Done</button>';
      document.body.append(colorDialog);
      let colorsAnchor;
      document.getElementById("all-colors").onclick = () => {
        colorsAnchor = document.createComment("colors"); chipsEl.replaceWith(colorsAnchor);
        colorDialog.querySelector(".color-grid").append(chipsEl); colorDialog.showModal();
      };
      colorDialog.querySelector("#color-search").oninput = event => {
        chipsEl.querySelectorAll(".chip").forEach(c => c.hidden = !c.textContent.toLowerCase().includes(event.target.value.toLowerCase()));
      };
      function closeColors() {
        colorsAnchor.replaceWith(chipsEl); chipsEl.querySelectorAll(".chip").forEach(c=>c.hidden=false);
        colorDialog.querySelector("#color-search").value=""; colorDialog.close();
      }
      colorDialog.querySelector("#color-done").onclick = closeColors;
      colorDialog.addEventListener("cancel", event => { event.preventDefault(); closeColors(); });
      document.getElementById("expand-toggle").addEventListener("click", () => {
        if (!queue.length) return;
        const state = cropState(queue[0]);
        state.mode = state.mode === "blur" ? "crop" : "blur";
        state.x = 0;
        state.y = 0;
        state.zoom = 1;
        cropMode = false;
        document.getElementById("crop-toggle").classList.remove("active");
        document.getElementById("crop-toggle").textContent = "Adjust crop";
        document.getElementById("crop-controls").classList.remove("visible");
        document.getElementById("expand-toggle").classList.toggle("active", state.mode === "blur");
        document.getElementById("expand-toggle").textContent = state.mode === "blur" ? "Use square crop" : "Expand background";
        const img = deck.lastElementChild?.querySelector("img.photo");
        if (img) applyCrop(img, queue[0]);
        hintEl.textContent = state.mode === "blur"
          ? "Full photo preserved over a softly blurred square background."
          : "Square crop restored.";
      });
      document.getElementById("ai-expand").addEventListener("click", () => {
        hintEl.textContent = "AI Expand is experimental and blocked here because pixel-locked OAuth masking is not available.";
      });
      document.getElementById("crop-zoom").addEventListener("input", (event) => {
        if (!queue.length) return;
        cropState(queue[0]).zoom = Number(event.target.value);
        const img = deck.lastElementChild?.querySelector("img.photo");
        if (img) applyCrop(img, queue[0]);
      });
      undoBtn.addEventListener("click", undo);
      window.addEventListener("keydown", (event) => {
        if (!root.isConnected || (options.native && !root.closest(".visible")) || /INPUT|TEXTAREA|SELECT/.test(event.target.tagName) || cropDialog.open || colorDialog.open) return;
        if (event.key === "ArrowRight") decide("approved");
        else if (event.key === "ArrowLeft") decide("rejected");
        else if (event.key.toLowerCase() === "u") undo();
        else if (/^[1-9]$/.test(event.key)) {
          const variant = variants[Number(event.key) - 1];
          if (variant) {
            selectedVariantId = variant.id;
            renderChips();
            updateHint();
          }
        }
      });

      if (options.navigate) for (const id of ["review-products", "back-to-products"]) document.getElementById(id).addEventListener("click", event => { event.preventDefault(); if (!busy) options.navigate(0); });
      (async () => {
        try {
          await load();
        } catch (error) {
          if (lifetime.signal.aborted) return;
          hintEl.textContent = `Failed to load: ${error.message}`;
        }
      })();
    
 return () => lifetime.abort();
};
