"use strict";
const el = (id) => document.getElementById(id);
const esc = (value) =>
  String(value ?? "").replace(
    /[&<>"']/g,
    (ch) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[
        ch
      ],
  );
const num = (value, digits = 0) =>
  value == null
    ? "—"
    : Number(value).toLocaleString("en-US", { maximumFractionDigits: digits });
const pct = (value, digits = 1) =>
  value == null ? "—" : `${num(value * 100, digits)}%`;
const usd = (cents) =>
  (cents / 100).toLocaleString("en-US", { style: "currency", currency: "USD" });
async function api(path, body, headers = {}) {
  const response = await fetch(path, {
    method: body === undefined ? "GET" : "POST",
    headers:
      body === undefined
        ? headers
        : { "Content-Type": "application/json", ...headers },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const result = await response.json();
  if (!response.ok) {
    const error = new Error(result.error || `HTTP ${response.status}`);
    error.status = response.status;
    throw error;
  }
  return result;
}
function notice(message, error = false) {
  el("status").textContent = message;
  el("status").classList.toggle("error", error);
  window.Studio?.celebrate(el("status"));
}
async function busy(button, action) {
  if (button.disabled) return;
  button.disabled = true;
  button.classList.add("is-loading");
  button.setAttribute("aria-busy", "true");
  try {
    await action();
  } catch (error) {
    notice(error.message, true);
  } finally {
    button.disabled = false;
    button.classList.remove("is-loading");
    button.removeAttribute("aria-busy");
  }
}
function download(name, value, type = "application/json") {
  const url = URL.createObjectURL(
    new Blob(
      [typeof value === "string" ? value : JSON.stringify(value, null, 2)],
      { type },
    ),
  );
  const link = document.createElement("a");
  link.href = url;
  link.download = name;
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 2000);
}
function table(headers, rows, highlight = -1) {
  return rows.length
    ? `<table><thead><tr>${headers.map((x) => `<th scope="col">${esc(x)}</th>`).join("")}</tr></thead><tbody>${rows.map((row, i) => `<tr class="${i === highlight ? "highlight" : ""}">${row.map((x) => `<td>${esc(x)}</td>`).join("")}</tr>`).join("")}</tbody></table>`
    : '<p class="empty">No records yet.</p>';
}
function metric(label, value, detail, accent = false) {
  return `<article class="metric"><span class="label">${esc(label)}${window.Studio?.icon(accent ? "bolt" : "chart") || ""}</span><strong class="${accent ? "metric-accent" : ""}">${esc(value)}</strong><small>${esc(detail)}</small></article>`;
}
function method(report) {
  el("method-content").innerHTML =
    `<div class="method-grid"><ul>${report.notes.map((x) => `<li>${esc(x)}</li>`).join("")}</ul><div>${report.sources.map((x) => `<a class="source-link" href="${esc(x.url)}" target="_blank" rel="noopener noreferrer">${esc(x.title)} ↗</a>`).join("")}<p class="caption">Source research checked November 14, 2026. This project implements a small local model of these ideas.</p></div></div>`;
}
// DOMAIN
let workspace, experiment;
const strategyName = {
  immediate: "Immediate retry",
  exponential: "Exponential backoff",
  full_jitter: "Full jitter",
};
function newKey() {
  el("key").value = `order-${crypto.randomUUID().slice(0, 8)}`;
}
async function refresh() {
  workspace = await api("/api/workspace");
  render();
}
function render() {
  const d = workspace,
    s = d.summary;
  el("export").disabled = false;
  el("metrics").innerHTML =
    metric(
      "Orders reserved",
      num(s.orders),
      usd(s.reserved_cents) + " in fictional goods",
    ) +
    metric(
      "Replay responses",
      num(s.replays),
      "No second inventory reservation",
      true,
    ) +
    metric(
      "Consumer effects",
      num(s.effects),
      "Unique local fulfillment effects",
    ) +
    metric(
      "Awaiting ACK",
      num(s.pending),
      `${s.dead_letter} dead letters · ${s.attempts} claims`,
    );
  el("clock").textContent =
    `${String(Math.floor(d.clock_ms / 60000)).padStart(2, "0")}:${String(Math.floor(d.clock_ms / 1000) % 60).padStart(2, "0")}`;
  const prior = el("sku").value;
  el("sku").innerHTML = d.inventory
    .map(
      (i) =>
        `<option value="${esc(i.sku)}">${esc(i.name)} · ${esc(usd(i.price_cents))} · ${i.stock} left</option>`,
    )
    .join("");
  if (d.inventory.some((i) => i.sku === prior)) el("sku").value = prior;
  else el("sku").value = "trail-pack";
  const events = Object.fromEntries(d.outbox.map((e) => [e.order_id, e]));
  el("orders").innerHTML = table(
    [
      "Order",
      "SKU / Qty",
      "Order stage",
      "Outbox state",
      "Claims",
      "Next eligible",
    ],
    d.orders.map((o) => {
      const e = events[o.id];
      return [
        o.id.slice(0, 10),
        `${o.sku} × ${o.quantity}`,
        o.stage.replaceAll("_", " "),
        e?.state.replaceAll("_", " "),
        num(e?.attempts),
        e?.state === "pending" ? `t+${num(e.available_ms / 1000, 2)}s` : "—",
      ];
    }),
  );
  el("delivery-log").innerHTML = table(
    ["Event", "Attempt", "Result", "Logical time"],
    d.delivery_log.map((log) => [
      log.event_id.slice(0, 10),
      log.attempt,
      log.result,
      `t+${num(log.clock_ms / 1000, 2)}s`,
    ]),
  );
  el("invariants").textContent = d.verification.valid
    ? "Stock & event counts reconcile"
    : "Invariant failure";
  method(d);
  renderHero();
  window.Studio?.refresh();
}
function renderHero() {
  const d = workspace,
    s = d.summary,
    acknowledged = d.outbox.filter((event) => event.state === "sent").length;
  const stages = [
    { name: "Reserved", value: s.orders, icon: "layers" },
    { name: "Consumed", value: s.effects, icon: "bolt" },
    { name: "ACK received", value: acknowledged, icon: "check" },
  ];
  el("hero-visual").dataset.active = String(s.pending > 0);
  el("hero-visual").innerHTML =
    `<div class="frame-header"><span>TRANSACTION MAP</span><span>t+${num(d.clock_ms / 1000)}s</span></div><div class="pipeline-display"><div class="pipeline-track" aria-hidden="true">${stages.map((stage, i) => `${i ? '<span class="pipeline-wire"></span>' : ""}<span class="pipeline-node ${stage.value ? "is-active" : ""}">${window.Studio?.icon(stage.icon) || ""}</span>`).join("")}</div><div class="pipeline-values">${stages.map((stage) => `<div><small>${stage.name}</small><strong>${num(stage.value)}</strong></div>`).join("")}</div></div><div class="frame-footer"><span><i class="status-dot"></i>${s.pending ? `${s.pending} AWAITING ACK` : s.dead_letter ? `${s.dead_letter} DEAD LETTERS` : s.orders ? "ALL EVENTS ACKNOWLEDGED" : "READY FOR YOUR FIRST ORDER"}</span><span>LOCAL EFFECTS</span></div>`;
}
async function compare() {
  experiment = await api("/api/experiment", {
    seed: Number(el("seed").value),
    clients: Number(el("clients").value),
    capacity: Number(el("capacity").value),
  });
  el("experiment-chart").innerHTML = experiment.results
    .map(
      (r) =>
        `<article class="bar-item"><label>${esc(strategyName[r.strategy])}</label><strong>${pct(r.completion_rate)} complete</strong><div class="bar-track"><i style="width:${r.completion_rate * 100}%"></i></div><small>${num(r.attempts)} attempts · ${num(r.amplification, 2)}× amplification</small></article>`,
    )
    .join("");
  el("experiment-table").innerHTML = table(
    ["Strategy", "Completed", "Failed", "Attempts / client", "Success p95"],
    experiment.results.map((r) => [
      strategyName[r.strategy],
      `${r.completed} / ${r.clients}`,
      r.clients - r.completed,
      `${num(r.amplification, 2)}×`,
      r.p95_success_latency_ms == null
        ? "—"
        : `${num(r.p95_success_latency_ms)} ms`,
    ]),
    2,
  );
  window.Studio?.refresh();
}
el("new-key").addEventListener("click", newKey);
el("order-form").addEventListener("submit", (event) => {
  event.preventDefault();
  busy(el("order"), async () => {
    const result = await api(
      "/api/orders",
      { sku: el("sku").value, quantity: Number(el("quantity").value) },
      { "Idempotency-Key": el("key").value },
    );
    el("order-result").textContent =
      `${result.replayed ? "REPLAY · Original response" : "CREATED · Inventory reserved"} / order ${result.order_id.slice(0, 10)} / ${usd(result.total_cents)}`;
    await refresh();
    notice(
      result.replayed
        ? "Request replayed. No extra inventory or outbox event was created."
        : "Order, stock reservation, response, and outbox event committed.",
    );
  });
});
el("worker-form").addEventListener("submit", (event) => {
  event.preventDefault();
  busy(el("dispatch"), async () => {
    const result = await api("/api/dispatch", {
      fault: el("fault").value,
      limit: 1,
    });
    el("worker-result").textContent = result.deliveries.length
      ? result.deliveries
          .map(
            (d) =>
              `Attempt ${d.attempt}: ${d.result}. New effect: ${d.new_effect ? "yes" : "no"}. ACK: ${d.acknowledged ? "yes" : "no"}.`,
          )
          .join(" ")
      : "No event is due. Pending retries may need a clock advance; exhausted events remain in dead-letter state.";
    await refresh();
    notice(
      result.deliveries.length
        ? "Worker step complete. Inspect the consumer effects and delivery log."
        : "No due event was claimed.",
    );
  });
});
el("advance").addEventListener("click", () =>
  busy(el("advance"), async () => {
    await api("/api/advance", { seconds: 60 });
    await refresh();
    notice(
      "Logical time advanced by 60 seconds. Pending retries and expired leases may now be eligible.",
    );
  }),
);
el("experiment-form").addEventListener("submit", (event) => {
  event.preventDefault();
  busy(el("run-experiment"), async () => {
    await compare();
    notice(
      `Retry experiment complete with seed ${experiment.seed}. Compare completion before latency.`,
    );
  });
});
el("export").addEventListener("click", () =>
  download("parcelguard-evidence.json", { workspace, experiment }),
);
newKey();
Promise.all([refresh(), compare()])
  .then(() =>
    notice(
      "Pipeline ready. Reserve an order, replay its key, then simulate a lost acknowledgement.",
    ),
  )
  .catch((error) => notice(error.message, true));
