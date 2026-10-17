// Hiển thị kết quả: thẻ tổng hợp, ảnh có đánh dấu (bật/tắt từng lớp), phóng to điểm lỗi, bảng lọc được, xuất file.
export const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

const RESULT_NAMES = {
  hot: "Pixel nóng", dead: "Pixel chết", stuck: "Pixel kẹt",
  ir_stuck: "IR kẹt", ir_dead: "IR chết", ir_hot: "IR nóng", ir_bad: "IR lỗi (outlier)",
};
const KIND_VI = { single: "đơn", cluster: "cụm", line: "đường" };
const INFO_ROWS = [
  ["camera", "Camera"], ["serial", "Serial"], ["firmware", "Firmware"], ["resolution_name", "Độ phân giải"],
  ["frames", "Số ảnh"], ["iso", "ISO"], ["exposure", "Phơi sáng"], ["bitrate", "Bitrate"], ["fps", "FPS"],
  ["temperature", "Nhiệt độ"], ["tester", "Người test"], ["note", "Ghi chú"],
];
const MAX_MARKS = 5000, MAX_ROWS = 1000, CROP = 31;   // CROP: vùng phóng to quanh điểm lỗi, px (lẻ để có tâm)

export function renderResults(out, data, firstFile) {
  const title = (r) => RESULT_NAMES[r.name] || r.name;
  const warns = data.notes.filter((n) => /^(WARNING|NOTE)/.test(n));
  const notes = data.notes.filter((n) => !/^(WARNING|NOTE)/.test(n));
  const total = data.results.reduce((a, r) => a + r.summary.total, 0);
  const info = data.info;

  out.innerHTML = `
    ${warns.map((w) => `<div class="msg warn">${esc(w)}</div>`).join("")}
    <section class="panel">
      <h2>Kết quả · ${total ? `${total} điểm lỗi` : '<span style="color:var(--ok)">không phát hiện lỗi</span>'}</h2>
      <div class="cards">${data.results.map((r) => `
        <div class="card" style="--c:${r.color}">
          <h3>${esc(title(r))}</h3>
          <div class="big${r.summary.total ? "" : " zero"}">${r.summary.total}</div>
          <div class="stats">vùng giữa A: <b>${r.summary.zoneA}</b> · đơn ${r.summary.single} · cụm ${r.summary.cluster} · đường ${r.summary.line}</div>
        </div>`).join("")}</div>
      <div class="toolbar">
        <button class="btn primary-soft" data-pdf>Tải báo cáo PDF</button>
        <button class="btn" data-dl="all">Tải tất cả (.json)</button>
        <button class="btn" data-dl="csv">Tải danh sách (.csv)</button>
        ${data.results.map((r, i) => `<button class="btn" data-dl="${i}">${esc(r.name)}.json</button>`).join("")}
      </div>
    </section>
    <section class="panel">
      <h2>Điều kiện chụp</h2>
      <dl class="info-grid">${INFO_ROWS.filter(([k]) => info[k] !== undefined).map(([k, label]) =>
        `<div><dt>${label}</dt><dd>${esc(info[k])}${k === "iso" ? ` <small>(${esc(info.iso_source)})</small>` : ""}</dd></div>`).join("")}</dl>
      <p class="notes">${notes.map(esc).join(" · ")}</p>
    </section>
    <section class="panel">
      <h2>Vị trí điểm lỗi</h2>
      <div class="toolbar" style="margin:0 0 10px">${data.results.map((r, i) => `
        <label class="chip" style="--c:${r.color}"><input type="checkbox" data-layer="${i}" checked>
          <span class="dot"></span>${esc(title(r))} (${r.defects.length})</label>`).join("")}
        <label class="chip"><input type="checkbox" data-zone checked>Khung vùng A</label>
      </div>
      <div class="viewer">
        <div>
          <div class="stage"><img alt="Ảnh đầu tiên của bộ thứ nhất"><svg viewBox="0 0 ${data.size.width} ${data.size.height}" preserveAspectRatio="none"></svg></div>
          <p class="cap">Ảnh đầu tiên của bộ thứ nhất · ${data.size.width}×${data.size.height}. Bấm vào vòng tròn hoặc dòng trong bảng để phóng to.</p>
        </div>
        <div class="zoom"><canvas width="${CROP * 8}" height="${CROP * 8}"></canvas><p class="zinfo">Chọn một điểm lỗi để xem cận cảnh (${CROP}×${CROP} px).</p></div>
      </div>
      <div class="toolbar">
        <select class="small" data-f="res"><option value="">Mọi kết quả</option>${data.results.map((r, i) => `<option value="${i}">${esc(title(r))}</option>`).join("")}</select>
        <select class="small" data-f="zone"><option value="">Mọi vùng</option><option>A</option><option>B</option></select>
        <select class="small" data-f="kind"><option value="">Mọi loại</option>${Object.entries(KIND_VI).map(([k, v]) => `<option value="${k}">${v}</option>`).join("")}</select>
        <span class="stats" data-count></span>
      </div>
      <div class="tbl"><table><thead><tr><th>#</th><th>Kết quả</th><th>x</th><th>y</th><th>Vùng</th><th>Loại</th><th>Số px</th></tr></thead><tbody></tbody></table></div>
    </section>`;

  const q = (s) => out.querySelector(s);
  q(".stage img").src = data.preview;
  const all = data.results.flatMap((r, ri) => r.defects.map((d, di) => ({ ...d, ri, di })));
  const svg = q("svg"), [zx0, zy0, zx1, zy1] = data.zone, rad = Math.max(6, data.size.width * 0.012);
  svg.innerHTML = `<rect data-zone x="${zx0}" y="${zy0}" width="${zx1 - zx0}" height="${zy1 - zy0}" fill="none" stroke="#ddd"
      stroke-dasharray="6 4" stroke-width="1.5" vector-effect="non-scaling-stroke"/>` +
    data.results.map((r, ri) => `<g data-layer="${ri}">${r.defects.slice(0, MAX_MARKS).map((d, di) =>
      `<circle cx="${d.x}" cy="${d.y}" r="${rad}" stroke="${r.color}" data-i="${ri}:${di}"><title>${esc(title(r))} · x=${d.x} y=${d.y} · ${KIND_VI[d.kind] || d.kind} · ${d.size} px</title></circle>`).join("")}</g>`).join("");

  // Bật/tắt lớp đánh dấu
  out.querySelectorAll("input[data-layer]").forEach((cb) => (cb.onchange = () =>
    (svg.querySelector(`g[data-layer="${cb.dataset.layer}"]`).style.display = cb.checked ? "" : "none")));
  q("input[data-zone]").onchange = (e) => (svg.querySelector("rect[data-zone]").style.display = e.target.checked ? "" : "none");

  // Bảng lọc được
  const tbody = q("tbody");
  let rows = all;
  const drawTable = () => {
    const f = Object.fromEntries([...out.querySelectorAll("[data-f]")].map((s) => [s.dataset.f, s.value]));
    rows = all.filter((d) => (f.res === "" || d.ri === Number(f.res)) && (!f.zone || d.zone === f.zone) && (!f.kind || d.kind === f.kind));
    tbody.innerHTML = rows.slice(0, MAX_ROWS).map((d, i) => `<tr data-row="${i}"><td>${i + 1}</td>
      <td><span class="dot" style="--c:${data.results[d.ri].color}"></span> ${esc(title(data.results[d.ri]))}</td>
      <td>${d.x}</td><td>${d.y}</td><td>${d.zone}</td><td>${KIND_VI[d.kind] || d.kind}</td><td>${d.size}</td></tr>`).join("")
      || '<tr><td colspan="7" class="stats">Không có điểm lỗi nào.</td></tr>';
    q("[data-count]").textContent = `${rows.length} điểm` + (rows.length > MAX_ROWS ? ` · hiện ${MAX_ROWS} đầu (tải CSV để xem đủ)` : "");
  };
  out.querySelectorAll("[data-f]").forEach((s) => (s.onchange = drawTable));
  drawTable();

  // Chọn điểm -> đánh dấu trên ảnh + phóng to
  const zoom = makeZoom(q("canvas"), q(".zinfo"), firstFile, q(".stage img"), data.size);
  const select = (d, row) => {
    out.querySelectorAll(".sel").forEach((e) => e.classList.remove("sel"));
    row?.classList.add("sel");
    svg.querySelector(`circle[data-i="${d.ri}:${d.di}"]`)?.classList.add("sel");
    zoom(d, title(data.results[d.ri]));
  };
  tbody.onclick = (e) => { const tr = e.target.closest("tr[data-row]"); if (tr) select(rows[Number(tr.dataset.row)], tr); };
  svg.onclick = (e) => {
    const c = e.target.closest("circle"); if (!c) return;
    const [ri, di] = c.dataset.i.split(":").map(Number);
    select({ ...data.results[ri].defects[di], ri, di });
  };
  if (all.length) select(all[0], tbody.querySelector("tr"));

  // Báo cáo PDF: gửi lại kết quả cho server dựng PDF (server không giữ ảnh giữa các lần gọi)
  const pdfBtn = q("[data-pdf]");
  pdfBtn.onclick = async () => {
    pdfBtn.disabled = true; pdfBtn.textContent = "Đang tạo PDF…";
    try {
      const res = await fetch("/api/report", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(data) });
      if (!res.ok) throw new Error((await res.json().catch(() => ({}))).error || `HTTP ${res.status}`);
      saveBlob(`${data.mode}_report.pdf`, await res.blob());
    } catch (e) { alertBox(out, `Không tạo được PDF: ${e.message}`); }
    finally { pdfBtn.disabled = false; pdfBtn.textContent = "Tải báo cáo PDF"; }
  };

  // Xuất file (cùng định dạng file .json của dòng lệnh)
  out.querySelectorAll("[data-dl]").forEach((b) => (b.onclick = () => {
    const k = b.dataset.dl, one = (r) => ({ info: data.info, params: data.params, summary: r.summary, defects: r.defects });
    if (k === "csv") {
      const lines = ["result,x,y,zone,kind,size", ...all.map((d) => [data.results[d.ri].name, d.x, d.y, d.zone, d.kind, d.size].join(","))];
      return download(`${data.mode}_defects.csv`, lines.join("\n"), "text/csv");
    }
    if (k === "all") return download(`${data.mode}_all.json`, JSON.stringify({ info: data.info, params: data.params, notes: data.notes,
      results: Object.fromEntries(data.results.map((r) => [r.name, { summary: r.summary, defects: r.defects }])) }, null, 1));
    const r = data.results[Number(k)];
    download(`${r.name}.json`, JSON.stringify(one(r), null, 1));
  }));
}

// Phóng to vùng quanh điểm lỗi từ ảnh gốc (đủ độ phân giải). Trình duyệt không đọc được (vd TIFF) -> dùng ảnh thu nhỏ.
function makeZoom(canvas, label, file, previewImg, size) {
  const ctx = canvas.getContext("2d"), probe = document.createElement("canvas").getContext("2d", { willReadFrequently: true });
  const source = createImageBitmap(file).then((bmp) => ({ img: bmp, s: 1 }))
    .catch(() => previewImg.decode().then(() => ({ img: previewImg, s: previewImg.naturalWidth / size.width, low: true })));
  return async (d, name) => {
    const { img, s, low } = await source, half = (CROP - 1) / 2, k = canvas.width / CROP;
    ctx.imageSmoothingEnabled = false;
    ctx.fillStyle = "#000"; ctx.fillRect(0, 0, canvas.width, canvas.height);
    ctx.drawImage(img, (d.x - half) * s, (d.y - half) * s, CROP * s, CROP * s, 0, 0, canvas.width, canvas.height);
    ctx.strokeStyle = "#ff3b30"; ctx.lineWidth = 2; ctx.strokeRect(half * k - 1, half * k - 1, k + 2, k + 2);
    probe.canvas.width = probe.canvas.height = 1;
    probe.drawImage(img, d.x * s, d.y * s, 1, 1, 0, 0, 1, 1);
    const [r, g, b] = probe.getImageData(0, 0, 1, 1).data;
    label.innerHTML = `<b>${esc(name)}</b> · x=${d.x}, y=${d.y}<br>vùng ${d.zone} · ${KIND_VI[d.kind] || d.kind} · ${d.size} px` +
      `<br>giá trị tâm ≈ R${r} G${g} B${b}` + (low ? "<br><i>trình duyệt không đọc được ảnh gốc, đang dùng ảnh thu nhỏ</i>" : "");
  };
}

function download(name, text, type = "application/json") { saveBlob(name, new Blob([text], { type })); }

function saveBlob(name, blob) {
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = name; a.click();
  setTimeout(() => URL.revokeObjectURL(a.href), 1000);
}

function alertBox(out, msg) {
  const d = document.createElement("div");
  d.className = "msg err"; d.textContent = msg;
  out.prepend(d);
}
