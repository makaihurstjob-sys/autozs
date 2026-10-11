/* Mobile destinations use existing guarded API actions; loading never writes. */
(() => {
 const el=document.getElementById('listings-view');let rows=[],products=[],filter='active',query='',generation=0;
 const esc=escapeHtml;const market=()=>document.body.dataset.marketplace;
 const dialog=document.createElement('dialog');dialog.className='workflow-dialog';document.body.append(dialog);
 function show(title,html){dialog.innerHTML=`<div class="workflow-header"><h2>${esc(title)}</h2><button class="workflow-button" data-close aria-label="Close">×</button></div>${html}`;dialog.querySelector('[data-close]').onclick=()=>dialog.close();if(!dialog.open)dialog.showModal();}
 async function perform(button,fn){button.disabled=true;try{await fn()}catch(e){let msg=dialog.querySelector('.workflow-error');if(!msg){msg=document.createElement('p');msg.className='workflow-error';msg.setAttribute('role','alert');dialog.append(msg)}msg.textContent=e.message}finally{if(button.isConnected&&!button.dataset.completed)button.disabled=false}}
 function image(url){if(!url)return '';try{const u=new URL(url,location.href);return ['http:','https:'].includes(u.protocol)?`<img src="${esc(u.href)}" alt="Product photo" loading="lazy">`:''}catch{return ''}}
 window.loadMobileListings=async()=>{
 const seq=++generation,m=market(),store=selectedStore;el.innerHTML='<p>Loading listings…</p>';
 try{
 const data=await Promise.all(m==='depop'?[api('/depop/variants'),api('/products')]:[api('/listings/queue'),api('/products')]);
 if(seq!==generation||m!==market()||store!==selectedStore)return;
 products=data[1];rows=data[0];
 if(store!=='all')rows=rows.filter(r=>m==='depop'?r.account_key===store:(!r.listing_account_id||r.listing_account_id===store));
 render();
 }catch(e){if(seq===generation)el.textContent=`Could not load listings: ${e.message}`}
 };
 function state(r){if(market()==='depop')return r.depop_listing_id?'active':r.status==='queued'?'scheduled':'drafts';return ['active','live','listed'].includes(r.listing_status)?'active':r.listing_status==='scheduled'?'scheduled':'drafts'}
 function render(){
 const shown=rows.filter(r=>state(r)===filter&&`${r.title} ${r.sku||''} ${r.color||''}`.toLowerCase().includes(query.toLowerCase()));
 el.innerHTML=`<div class="workflow-header"><h2>Listings</h2><span>${shown.length}</span></div><input class="workflow-search" aria-label="Search listings" placeholder="Search title, SKU or color" value="${esc(query)}"><div class="workflow-filters">${['active','drafts','scheduled'].map(f=>`<button type="button" data-filter="${f}" class="${f===filter?'active':''}">${f[0].toUpperCase()+f.slice(1)} ${rows.filter(r=>state(r)===f).length}</button>`).join('')}</div><div id="workflow-results">${shown.map(r=>{const p=products.find(p=>p.id===r.product_id);return `<button class="workflow-row" data-listing="${market()==='depop'?r.id:r.product_id}">${image(p?.images?.[0]?.image_url)}<span><strong>${esc(r.title)}</strong><small>${r.price==null?'Price pending':'$'+Number(r.price).toFixed(2)} · ${esc(r.color||state(r))}</small></span><b>›</b></button>`}).join('')||'<p>No listings in this view.</p>'}</div>`;
 el.querySelector('input').oninput=e=>{query=e.target.value;const start=e.target.selectionStart;render();const input=el.querySelector('input');input.focus();input.setSelectionRange(start,start)};
 el.querySelectorAll('[data-filter]').forEach(b=>b.onclick=()=>{filter=b.dataset.filter;render()});
 el.querySelectorAll('[data-listing]').forEach(b=>b.onclick=()=>openListing(Number(b.dataset.listing)));
 }
 function field(name,label,value,type='text'){return `<label class="workflow-field">${label}<input name="${name}" type="${type}" value="${esc(String(value??''))}" ${type==='number'?'min="0.01" step="0.01"':''}></label>`}
 async function openListing(id){
 const depop=market()==='depop';const r=rows.find(r=>depop?r.id===id:r.product_id===id);if(!r)return;
 const p=products.find(p=>p.id===r.product_id);show(depop?'Depop listing':'Draft details','<p>Loading details…</p>');
 try{
 const readiness=depop?null:await api(`/products/${id}/listing-readiness`);
 const images=p?.images||[];
 show(depop?'Depop listing':'Draft details',`<div class="workflow-gallery">${images.filter(i=>!depop||(r.image_ids||[]).includes(i.id)).map(i=>image(i.image_url)).join('')}</div><form id="listing-editor">${field('title','Title',r.title)}${depop?field('price','Price (USD)',r.price,'number')+field('color','Color',r.color)+field('shipping_method','Shipping method',r.shipping_method)+`<label class="workflow-field">Description<textarea name="description" rows="3">${esc(r.description||'')}</textarea></label>`:`<div class="workflow-status">${esc((readiness.missing_manual||[]).join(' · ')||'Manual listing checks passed')}<br>${esc((readiness.warnings||[]).join(' · '))}</div><p>Price and shipping use the existing supplier and listing rules.</p>`}<div class="workflow-actions"><button class="workflow-button primary" type="submit">Save draft</button></div></form>${!depop&&!r.listing_id?`${field('ebayWhen','Schedule time (your local time)','','datetime-local')}<button class="workflow-button primary" id="schedule-ebay" ${!readiness.manual_ready||selectedStore==='all'?'disabled':''}>Schedule draft</button><p>Choose one eBay store and complete listing checks before scheduling.</p>`:''}${depop&&!r.depop_listing_id?`${field('when','Schedule time (your local time)','','datetime-local')}<p>Scheduling uses the account’s existing boost settings.</p><button class="workflow-button primary" id="schedule-one">Schedule listing</button>`:''}<a class="workflow-button" href="${esc(dashboardUrl)}">Full product controls ?</a>`);
 dialog.querySelector('form').onsubmit=e=>{e.preventDefault();const form=e.target;const data=Object.fromEntries(new FormData(form));const btn=form.querySelector('button');perform(btn,async()=>{if(depop){data.price=Number(data.price);await api(`/depop/variants/${id}`,{method:'PATCH',body:JSON.stringify(data)});Object.assign(r,data)}else{await api(`/products/${id}/capture`,{method:'PATCH',body:JSON.stringify({title:data.title})});r.title=data.title}btn.textContent='Saved';render()})};
 const ebaySchedule=dialog.querySelector('#schedule-ebay');if(ebaySchedule)ebaySchedule.onclick=()=>perform(ebaySchedule,async()=>{const raw=dialog.querySelector('[name="ebayWhen"]').value;if(!raw||new Date(raw)<=new Date())throw new Error('Choose a future schedule time.');const result=await api('/listing-jobs',{method:'POST',body:JSON.stringify({product_ids:[id],ebay_account_key:selectedStore,action:'create_draft',scheduled_for:new Date(raw).toISOString()})});if(!result.length)throw new Error('No draft was queued. Check product readiness.');ebaySchedule.textContent='Scheduled';ebaySchedule.dataset.completed='1'});
 const schedule=dialog.querySelector('#schedule-one');if(schedule)schedule.onclick=()=>perform(schedule,async()=>{const raw=dialog.querySelector('[name="when"]').value;if(!raw||new Date(raw)<=new Date())throw new Error('Choose a future schedule time.');await api('/depop/jobs',{method:'POST',body:JSON.stringify({variant_id:id,scheduled_for:new Date(raw).toISOString()})});schedule.textContent='Scheduled';schedule.disabled=true;schedule.dataset.completed='1';r.status='queued';render()});
 }catch(e){show('Details unavailable',`<p class="workflow-error">${esc(e.message)}</p>`)}
 }
 document.addEventListener('click',async e=>{
 const a=e.target.closest('[data-job-detail]');if(!a)return;e.preventDefault();const kind=a.dataset.jobKind,id=Number(a.dataset.jobDetail);show('Queue details','<p>Loading…</p>');
 try{
 const path=kind==='Price refresh'?'/source-refresh/jobs':kind==='Listing'?(market()==='depop'?'/depop/jobs':'/listing-jobs?limit=1000&lite=1'):null;
 if(!path){show('Queue details',`<p>Revision details are available in the full dashboard.</p><a href="${esc(dashboardUrl)}">Open details</a>`);return}
 const data=await api(path),job=data.find(j=>j.id===id);if(!job)throw new Error('Job no longer available.');
 show('Queue details',`<h3>${esc(job.title||kind)}</h3><div class="workflow-status">${esc(job.status)}<br>${esc(job.message||'')}<br>Attempts: ${Number(job.attempts||0)}<br>Last update: ${esc(formatDate(job.updated_at))}</div>${kind==='Price refresh'&&['failed','needs_review'].includes(job.status)?'<button class="workflow-button primary" id="retry-check">Retry check</button>':''}<div class="workflow-actions"><a class="workflow-button" href="${esc(dashboardUrl)}">View product ?</a></div>`);
 const retry=dialog.querySelector('#retry-check');if(retry)retry.onclick=()=>perform(retry,async()=>{await api('/source-refresh/batches',{method:'POST',body:JSON.stringify({product_ids:[job.product_id],limit:1,force:true,auto_claim:false})});retry.textContent='Check queued'});
 }catch(e){show('Queue details',`<p class="workflow-error">${esc(e.message)}</p>`)}
 });
 const store=document.getElementById('store-picker');store.addEventListener('mousedown',e=>{if(store.disabled)return;e.preventDefault();show('Choose store',`<form id="store-sheet">${[...store.options].map(o=>`<label class="workflow-store"><input type="radio" name="store" value="${esc(o.value)}" ${o.value===store.value?'checked':''}>${esc(o.text)}</label>`).join('')}<div class="workflow-actions"><button class="workflow-button primary">Apply</button></div></form>`);dialog.querySelector('form').onsubmit=e=>{e.preventDefault();store.value=new FormData(e.target).get('store');store.dispatchEvent(new Event('change'));dialog.close()}});
 if(selectedView==='listings')window.loadMobileListings();
})();

