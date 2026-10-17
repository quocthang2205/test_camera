// Điều khiển form: chọn loại test, thả ảnh, điều kiện chụp, thông số phân tích, gửi lên server.
// Form tự dựng từ /api/config nên thêm thông số ở Python (analysis_params.SPEC) là tự hiện ở đây.
import { renderResults, esc } from "./results-view.js";

const MODE_NAMES = { hot: "Pixel nóng", dead: "Pixel chết", stuck: "Pixel kẹt", ir: "Camera nhiệt" };
const SLOT_LABELS = {
  dark: ["Ảnh tối", "che kín ống kính"], white: ["Ảnh nền trắng", "sáng đều 60–80%, không cháy"],
  red: ["Màn hình đỏ", "toàn khung đỏ"], green: ["Màn hình xanh lá", "toàn khung xanh lá"],
  blue: ["Màn hình xanh dương", "toàn khung xanh dương"],
  t1: ["Nhiệt độ 1", "bề mặt đồng nhiệt"], t2: ["Nhiệt độ 2", "nhiệt độ khác t1"],
};
const IMG_RE = /\.(png|jpe?g|bmp|tiff?)$/i;

let CFG = null, mode = null, frames = 5, files = {}, thumbs = {}, busy = false;
const $ = (id) => document.getElementById(id);

// Ghi nhớ giá trị form trong trình duyệt này (tiện khi đo nhiều lần); lỗi storage thì bỏ qua
const store = {
  get(k, d) { try { return JSON.parse(localStorage.getItem("pixcheck." + k)) ?? d; } catch { return d; } },
  set(k, v) { try { localStorage.setItem("pixcheck." + k, JSON.stringify(v)); } catch { /* bỏ qua */ } },
};
const fieldVals = store.get("fields", {}), paramVals = store.get("params", {});

/* ---------- Bước 1: loại test ---------- */
function buildModes() {
  $("modes").innerHTML = Object.entries(CFG.modes).map(([m, c]) =>
    `<button class="mode" role="radio" data-m="${m}"><b>${MODE_NAMES[m] || m}</b><span>${esc(c.help)}</span></button>`).join("");
  $("modes").querySelectorAll(".mode").forEach((b) => (b.onclick = () => selectMode(b.dataset.m)));
}

function selectMode(m) {
  if (busy) return;
  mode = m; store.set("mode", m);
  Object.values(thumbs).flat().forEach(URL.revokeObjectURL);
  files = {}; thumbs = {};
  $("modes").querySelectorAll(".mode").forEach((b) => {
    b.classList.toggle("on", b.dataset.m === m); b.setAttribute("aria-checked", b.dataset.m === m);
  });
  $("frames-box").hidden = !CFG.modes[m].frames;
  $("slot-hint").hidden = CFG.modes[m].slots.length < 2;
  $("slots").replaceChildren(...CFG.modes[m].slots.map(makeSlot));
  $("out").innerHTML = ""; $("status").textContent = "";
  buildParams(); refresh();
}

/* ---------- Bước 2: ảnh ---------- */
function makeSlot(slot) {
  const [title, hint] = SLOT_LABELS[slot] || [slot, ""];
  const el = document.createElement("label");
  el.className = "drop"; el.dataset.slot = slot;
  el.innerHTML = `<span class="t">${esc(title)}</span><span class="hint">${esc(hint)}</span>
    <div class="thumbs"></div><div class="count">Kéo thả hoặc bấm để chọn ảnh</div>
    <button class="clear" title="Bỏ ảnh" hidden>×</button><input type="file" accept="image/*,.tif,.tiff" multiple>`;
  const input = el.querySelector("input");
  input.onchange = () => setFiles(slot, input.files);
  el.ondragover = (e) => { e.preventDefault(); e.stopPropagation(); el.classList.add("over"); };
  el.ondragleave = () => el.classList.remove("over");
  el.ondrop = (e) => { e.preventDefault(); e.stopPropagation(); el.classList.remove("over"); hideVeil(); setFiles(slot, e.dataTransfer.files); };
  el.querySelector(".clear").onclick = (e) => { e.preventDefault(); input.value = ""; setFiles(slot, []); };
  return el;
}

function setFiles(slot, list) {
  (thumbs[slot] || []).forEach(URL.revokeObjectURL);
  files[slot] = [...list].filter((f) => f.type.startsWith("image/") || IMG_RE.test(f.name))
    .sort((a, b) => a.name.localeCompare(b.name, undefined, { numeric: true }));
  thumbs[slot] = files[slot].slice(0, 5).map((f) => URL.createObjectURL(f));
  refresh();
}

// Thả nhiều ảnh vào trang: một ô -> vào ô đó; nhiều ô -> xếp theo tên file chứa tên ô (dark_01.png -> dark)
function routeFiles(list) {
  const slots = CFG.modes[mode].slots, imgs = [...list].filter((f) => IMG_RE.test(f.name) || f.type.startsWith("image/"));
  if (slots.length === 1) return setFiles(slots[0], imgs);
  const buckets = {}, missed = [];
  imgs.forEach((f) => {
    const s = slots.find((s) => new RegExp(`(^|[^a-z0-9])${s}([^a-z]|$)`, "i").test(f.name));
    s ? (buckets[s] ||= []).push(f) : missed.push(f.name);
  });
  Object.entries(buckets).forEach(([s, l]) => setFiles(s, l));
  $("status").textContent = missed.length
    ? `${missed.length} ảnh không khớp tên ô nào (${missed.slice(0, 3).join(", ")}${missed.length > 3 ? "…" : ""}): thả trực tiếp vào ô.` : "";
}

function needed() { return CFG.modes[mode].frames ? frames : CFG.modes[mode].min; }

function refresh() {
  const min = needed();
  let ready = true;
  document.querySelectorAll(".drop").forEach((el) => {
    const slot = el.dataset.slot, n = (files[slot] || []).length, cnt = el.querySelector(".count");
    cnt.textContent = !n ? "Kéo thả hoặc bấm để chọn ảnh" : n < min ? `${n} ảnh · thiếu ${min - n}`
      : `✓ ${n} ảnh` + (CFG.modes[mode].frames && n > min ? ` · dùng ${min} ảnh đầu` : "");
    cnt.classList.toggle("miss", n > 0 && n < min);
    el.querySelector(".thumbs").innerHTML = (thumbs[slot] || []).map((u) => `<img src="${u}" alt="" onerror="this.remove()">`).join("")
      + (n > 5 ? `<span class="more">+${n - 5}</span>` : "");
    el.querySelector(".clear").hidden = !n;
    el.classList.toggle("ok", n >= min);
    if (n < min) ready = false;
  });
  $("run").disabled = !ready || busy;
}

/* ---------- Bước 3: điều kiện chụp ---------- */
function buildFields() {
  $("fields").innerHTML = CFG.fields.map((f) =>
    `<label class="f${f.key === "note" ? " wide" : ""}">${esc(f.label)}
      <input data-k="${f.key}" ${f.kind === "text" ? 'type="text"' : 'type="number" step="any" min="0"'}
        placeholder="${esc(f.example)}" value="${esc(fieldVals[f.key] ?? "")}"></label>`).join("");
  $("fields").oninput = (e) => { fieldVals[e.target.dataset.k] = e.target.value; store.set("fields", fieldVals); };
}

/* ---------- Bước 4: thông số phân tích ---------- */
function buildParams() {
  const specs = CFG.params.filter((s) => s.modes.includes(mode));
  let html = "", group = null;
  specs.forEach((s) => {
    if (s.group !== group) { group = s.group; html += `<div class="pgroup">${esc(group)}</div>`; }
    html += `<div class="prow f"><label for="p-${s.key}">${esc(s.label)}</label>
      <input id="p-${s.key}" data-k="${s.key}" type="number" min="${s.min}" max="${s.max}" step="${s.step}"
        placeholder="${s.default}" value="${esc(paramVals[s.key] ?? "")}">
      <small>${esc(s.help)} · mặc định ${s.default}</small></div>`;
  });
  $("params").innerHTML = html;
  markChanged();
}

function markChanged() {
  let n = 0;
  $("params").querySelectorAll("input").forEach((i) => {
    const spec = CFG.params.find((s) => s.key === i.dataset.k);
    const on = i.value !== "" && Number(i.value) !== spec.default;
    i.classList.toggle("changed", on); n += on;
  });
  $("changed-badge").hidden = !n;
  $("changed-badge").textContent = `${n} thay đổi`;
}

$("params").oninput = (e) => {
  paramVals[e.target.dataset.k] = e.target.value; store.set("params", paramVals); markChanged();
};

/* ---------- Gửi phân tích ---------- */
function run() {
  if ($("run").disabled) return;
  const fd = new FormData(), slots = CFG.modes[mode].slots;
  slots.forEach((slot) => (files[slot] || []).forEach((f) => fd.append(slot, f, f.name)));
  if (CFG.modes[mode].frames) fd.append("frames", frames);
  CFG.fields.forEach((f) => fd.append(f.key, fieldVals[f.key] ?? ""));
  CFG.params.filter((s) => s.modes.includes(mode)).forEach((s) => fd.append("p_" + s.key, paramVals[s.key] ?? ""));

  busy = true; refresh(); $("out").innerHTML = "";
  const t0 = performance.now(), xhr = new XMLHttpRequest();
  const setStatus = (html) => ($("status").innerHTML = html);
  setStatus('Đang tải ảnh lên… <div class="bar"><i style="width:0"></i></div>');
  xhr.upload.onprogress = (e) => {
    if (!e.lengthComputable) return;
    const pct = Math.round((e.loaded / e.total) * 100);
    setStatus(pct < 100 ? `Đang tải ảnh lên… ${pct}% <div class="bar"><i style="width:${pct}%"></i></div>`
      : '<span class="spin"></span>Đang phân tích…');
  };
  xhr.upload.onload = () => setStatus('<span class="spin"></span>Đang phân tích…');
  const done = () => { busy = false; refresh(); };
  xhr.onload = () => {
    let data; try { data = JSON.parse(xhr.responseText); } catch { data = { error: `Lỗi máy chủ (HTTP ${xhr.status})` }; }
    done();
    if (xhr.status !== 200 || data.error) return fail(data.error || `HTTP ${xhr.status}`);
    setStatus(`Xong trong ${((performance.now() - t0) / 1000).toFixed(1)} giây.`);
    renderResults($("out"), data, files[slots[0]][0]);
    $("out").scrollIntoView({ behavior: "smooth", block: "start" });
  };
  xhr.onerror = () => { done(); fail("không kết nối được máy chủ"); };
  xhr.open("POST", `/api/analyze/${mode}`); xhr.send(fd);
}

function fail(msg) {
  $("status").textContent = "";
  $("out").innerHTML = `<div class="msg err"><b>Lỗi:</b> ${esc(msg)}</div>`;
}

/* ---------- Sự kiện chung ---------- */
const veil = $("veil");
const hideVeil = () => veil.classList.remove("on");
window.addEventListener("dragover", (e) => { e.preventDefault(); if (mode && !busy) veil.classList.add("on"); });
veil.addEventListener("dragleave", (e) => { if (e.target === veil) hideVeil(); });
window.addEventListener("drop", (e) => { e.preventDefault(); hideVeil(); if (mode && !busy) routeFiles(e.dataTransfer.files); });
window.addEventListener("keydown", (e) => { if ((e.ctrlKey || e.metaKey) && e.key === "Enter") run(); });

$("run").onclick = run;
$("frames").onclick = (e) => {
  const b = e.target.closest("button"); if (!b) return;
  frames = Number(b.dataset.v); store.set("frames", frames);
  $("frames").querySelectorAll("button").forEach((x) => x.classList.toggle("on", x === b));
  refresh();
};
$("clear-fields").onclick = () => {
  Object.keys(fieldVals).forEach((k) => delete fieldVals[k]); store.set("fields", fieldVals); buildFields();
};
$("reset-params").onclick = () => {
  Object.keys(paramVals).forEach((k) => delete paramVals[k]); store.set("params", paramVals); buildParams();
};

fetch("/api/config").then((r) => r.json()).then((cfg) => {
  CFG = cfg;
  frames = store.get("frames", cfg.default_frames);
  $("frames").querySelectorAll("button").forEach((x) => x.classList.toggle("on", Number(x.dataset.v) === frames));
  buildModes(); buildFields();
  const last = store.get("mode", null);
  selectMode(cfg.modes[last] ? last : Object.keys(cfg.modes)[0]);
}).catch(() => fail("không kết nối được máy chủ. Hãy chạy python web_app.py"));
