"""The customer-cards page: log customers, their wishes and terms, and approve matches. No code."""

PAGE = r"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Customer cards</title>
<style>
:root{--bg:#f6f5f2;--card:#fff;--fg:#1c1c1a;--mut:#6b6a64;--line:#e2e0da;--acc:#2f5bd3;--ok:#1f7a4d;--no:#a23b3b;--chip:#eef1fb}
@media (prefers-color-scheme:dark){:root{--bg:#141413;--card:#1d1d1b;--fg:#eceae4;--mut:#9d9b94;--line:#33322e;--acc:#7c9cff;--ok:#5cc28f;--no:#e07b7b;--chip:#252a3a}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:15px/1.45 system-ui,-apple-system,sans-serif}
main{max-width:860px;margin:0 auto;padding:18px 16px 60px}h1{font-size:21px;margin:0 0 2px}p.sub{color:var(--mut);margin:0 0 16px}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:14px 16px;margin:0 0 14px}
.card h2{font-size:17px;margin:0}.meta{color:var(--mut);font-size:13px;margin:2px 0 8px}
.row{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:8px}
label{display:block;font-size:12px;color:var(--mut);margin:8px 0 3px}
input,select,textarea{width:100%;padding:8px 9px;border:1px solid var(--line);border-radius:8px;background:transparent;color:inherit;font:inherit}
textarea{min-height:52px}button{padding:8px 13px;border:0;border-radius:8px;background:var(--acc);color:#fff;font:inherit;cursor:pointer}
button.ghost{background:transparent;color:var(--acc);border:1px solid var(--line)}button.ok{background:var(--ok)}button.no{background:var(--no)}
.chips{display:flex;flex-wrap:wrap;gap:6px;margin:6px 0}.chip{background:var(--chip);border-radius:999px;padding:3px 10px;font-size:13px}
.chip button{background:none;color:var(--mut);padding:0 0 0 6px;border:0}
.match{border-top:1px solid var(--line);padding:9px 0;display:flex;gap:10px;align-items:flex-start;justify-content:space-between}
.match a{color:inherit}.fit{color:var(--ok);font-weight:600}.dec{font-size:12px;color:var(--mut)}
details summary{cursor:pointer;color:var(--acc);margin-top:6px}.toast{position:fixed;bottom:16px;left:50%;transform:translateX(-50%);background:var(--fg);color:var(--bg);padding:8px 14px;border-radius:8px;display:none}
</style></head><body><main>
<h1>Customer cards</h1><p class="sub">Who's buying, what they want, what counts as a deal for them, and the matches waiting for your call.</p>
<div class="card"><h2>New customer</h2>
<div class="row"><div><label>Name</label><input id="n_name"></div><div><label>Phone</label><input id="n_phone" inputmode="tel"></div>
<div><label>Email</label><input id="n_email" inputmode="email"></div></div>
<div class="row"><div><label>ZIP</label><input id="n_zip" inputmode="numeric"></div><div><label>Miles</label><input id="n_miles" inputmode="numeric" placeholder="150"></div>
<div><label>Discount threshold</label><input id="n_discount" placeholder="30%"></div><div><label>Budget</label><input id="n_budget" placeholder="$15,000"></div></div>
<label>Notes</label><textarea id="n_notes"></textarea><p><button onclick="newCard()">Save customer</button></p></div>
<div id="cards"></div><div class="toast" id="toast"></div>
<script>
const token = new URLSearchParams(location.search).get("token") || "";
const H = {"Content-Type":"application/json","Authorization":"Bearer "+token};
const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const money = v => v ? "$"+Number(v).toLocaleString(undefined,{maximumFractionDigits:0}) : "";
const pct = v => v ? Math.round(v*100)+"%" : "";
function toast(t){const el=document.getElementById("toast");el.textContent=t;el.style.display="block";setTimeout(()=>el.style.display="none",1800)}
async function call(body){const r=await fetch("/api/customers",{method:"POST",headers:H,body:JSON.stringify(body)});return r.json()}
async function load(){const r=await fetch("/api/customers",{headers:H});const d=await r.json();render(d.customers||[])}
function v(id){return (document.getElementById(id)||{}).value||""}
async function newCard(){const card={name:v("n_name"),phone:v("n_phone"),email:v("n_email"),zip:v("n_zip"),miles:v("n_miles"),discount:v("n_discount"),budget:v("n_budget"),notes:v("n_notes")};
 if(!card.name) return toast("Name first");const d=await call({action:"save_card",card});toast(d.status==="SUCCESS"?"Saved":d.message);
 document.querySelectorAll("[id^=n_]").forEach(e=>e.value="");load()}
async function saveCard(i,name){const card={name,phone:v("p"+i),email:v("e"+i),zip:v("z"+i),miles:v("m"+i),discount:v("d"+i),budget:v("b"+i),notes:v("t"+i)};
 const d=await call({action:"save_card",card});toast(d.status==="SUCCESS"?"Saved":d.message);load()}
async function addWant(i,name){const want={name:v("wi"+i),q:v("wq"+i),max_price:v("wm"+i),discount:v("wd"+i),hunt:v("wh"+i),notify:v("wn"+i)};
 if(!want.name) return toast("What do they want?");const d=await call({action:"add_want",customer:name,want});toast(d.status==="SUCCESS"?"Watching":d.message);load()}
async function dropWant(name,item){await call({action:"remove_want",customer:name,name:item});toast("Removed");load()}
async function decide(name,id,decision){await call({action:"decide",customer:name,lead_id:id,decision});toast(decision==="approved"?"Approved":"Passed");load()}
function render(cards){document.getElementById("cards").innerHTML=cards.map((c,i)=>`
<div class="card"><h2>${esc(c.name)}</h2>
<div class="meta">${[c.phone,c.email,c.zip&&(c.zip+(c.miles?" · "+c.miles+" mi":"")),c.discount&&("wants "+pct(c.discount)+" under value"),c.budget&&("budget "+money(c.budget))].filter(Boolean).map(esc).join(" · ")}</div>
${c.notes?`<div>${esc(c.notes)}</div>`:""}
<div class="chips">${(c.wants||[]).map(w=>`<span class="chip">${esc(w.name)}${w.max_price?" ≤ "+money(w.max_price):""}${w.discount?" · "+pct(w.discount)+" off":""}<button title="remove" onclick="dropWant('${esc(c.name)}','${esc(w.name)}')">✕</button></span>`).join("")||'<span class="dec">No wants yet</span>'}</div>
<details><summary>Add a want</summary><div class="row"><div><label>Item</label><input id="wi${i}" placeholder="Mazdaspeed6"></div>
<div><label>eBay search (optional)</label><input id="wq${i}" placeholder="(mazdaspeed6, mazdaspeed 6)"></div></div>
<div class="row"><div><label>Max price</label><input id="wm${i}"></div><div><label>Discount</label><input id="wd${i}" placeholder="25%"></div>
<div><label>Kind</label><select id="wh${i}"><option value="auto">auto</option><option>vehicle</option><option>jewelry</option><option>electronics</option><option>equipment</option></select></div>
<div><label>Tell me</label><select id="wn${i}"><option value="all">every match</option><option value="deals">deals only</option></select></div></div>
<p><button onclick="addWant(${i},'${esc(c.name)}')">Add want</button></p></details>
<details><summary>Edit card</summary><div class="row"><div><label>Phone</label><input id="p${i}" value="${esc(c.phone)}"></div><div><label>Email</label><input id="e${i}" value="${esc(c.email)}"></div>
<div><label>ZIP</label><input id="z${i}" value="${esc(c.zip)}"></div><div><label>Miles</label><input id="m${i}" value="${esc(c.miles)}"></div></div>
<div class="row"><div><label>Discount</label><input id="d${i}" value="${c.discount?pct(c.discount):""}"></div><div><label>Budget</label><input id="b${i}" value="${esc(c.budget)}"></div></div>
<label>Notes</label><textarea id="t${i}">${esc(c.notes)}</textarea><p><button class="ghost" onclick="saveCard(${i},'${esc(c.name)}')">Save card</button></p></details>
${(c.matches||[]).length?"<h3 style='font-size:14px;margin:12px 0 0'>Matches</h3>":""}
${(c.matches||[]).map(m=>`<div class="match"><div><a href="${esc(m.url)}" target="_blank" rel="noopener">${esc(m.title)}</a>
 <div class="dec">${money(m.value)} · score ${m.score} ${m.fits?'· <span class="fit">fits their terms</span>':""}${m.decision?" · "+esc(m.decision):""}</div></div>
 <div style="white-space:nowrap">${m.decision?"":`<button class="ok" onclick="decide('${esc(c.name)}','${esc(m.lead_id)}','approved')">Approve</button> <button class="no" onclick="decide('${esc(c.name)}','${esc(m.lead_id)}','passed')">Pass</button>`}</div></div>`).join("")}
</div>`).join("")}
load();
</script></main></body></html>"""
