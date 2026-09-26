import { getActiveInstance, subscribe } from "../store.js";
import { renderMarkdown } from "../markdown.js";

/** @param {Record<string, unknown> | null} table */
function renderTable(table) {
  if (!table || !Array.isArray(table.columns) || !Array.isArray(table.rows)) {
    return "<p class=\"dashboard-empty\">Live dataset will appear here after the first extract.</p>";
  }
  const columns = /** @type {string[]} */ (table.columns);
  const rows = /** @type {string[][]} */ (table.rows);
  if (!columns.length) {
    return "<p class=\"dashboard-empty\">No columns yet.</p>";
  }
  const header = "| " + columns.join(" | ") + " |";
  const sep = "| " + columns.map(() => "---").join(" | ") + " |";
  const body = rows
    .map((row) => {
      const cells = columns.map((_, i) => String(row[i] ?? "").replace(/\|/g, "\\|"));
      return "| " + cells.join(" | ") + " |";
    })
    .join("\n");
  return renderMarkdown([header, sep, body].join("\n"));
}

/** @param {HTMLElement} root */
export function mountDashboard(root) {
  root.innerHTML = `
    <div class="dashboard-head">
      <h2 class="dashboard-title">Live dataset</h2>
      <span class="dashboard-count" id="dashboard-count"></span>
    </div>
    <div class="dashboard-table msg-markdown" id="dashboard-table"></div>
  `;

  const tableEl = /** @type {HTMLElement} */ (root.querySelector("#dashboard-table"));
  const countEl = /** @type {HTMLElement} */ (root.querySelector("#dashboard-count"));

  async function loadDashboard(instanceId) {
    const res = await fetch(`/api/instances/${instanceId}/dashboard`);
    if (!res.ok) return;
    const data = await res.json();
    countEl.textContent = data.rows_total ? `${data.rows_total} rows` : "";
    tableEl.innerHTML = renderTable(data.table);
  }

  document.addEventListener("awdax:dataset", (ev) => {
    const table = /** @type {CustomEvent} */ (ev).detail;
    tableEl.innerHTML = renderTable(table);
    if (table && typeof table.row_count === "number") {
      countEl.textContent = `${table.row_count} rows`;
    } else if (table && Array.isArray(table.rows)) {
      countEl.textContent = `${table.rows.length} rows`;
    }
  });

  /** @type {string} */
  let loadedFor = "";

  subscribe((state) => {
    if (!state.ready || !state.activeId) return;
    if (state.activeId === loadedFor) {
      const active = getActiveInstance();
      if (active?.dataset_row_count != null && !countEl.textContent) {
        countEl.textContent = active.dataset_row_count
          ? `${active.dataset_row_count} rows`
          : "";
      }
      return;
    }
    loadedFor = state.activeId;
    loadDashboard(state.activeId).catch(console.error);
  });
}
