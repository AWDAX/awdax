const ACTIVE_KEY = "awdax.activeInstanceId";

/** @typedef {{ id: number; role: "user" | "bot"; text: string; created_at: string }} Message */
/** @typedef {{ id: string; title: string; createdAt: number; updatedAt: number; messages: Message[]; live_enabled: boolean; dataset_row_count: number; live_status?: Record<string, unknown> }} Instance */
/** @typedef {{ activeId: string; instances: Instance[]; ready: boolean }} ChatState */

/** @type {Set<(state: ChatState) => void>} */
const listeners = new Set();

/** @type {ChatState} */
let state = { activeId: "", instances: [], ready: false };

/** @returns {ChatState} */
export function getState() {
  return state;
}

/** @param {Partial<ChatState>} patch */
function commit(patch) {
  state = { ...state, ...patch };
  listeners.forEach((fn) => fn(state));
}

/** @param {(state: ChatState) => void} fn */
export function subscribe(fn) {
  listeners.add(fn);
  fn(state);
  return () => listeners.delete(fn);
}

/** @param {unknown} body */
async function api(path, options = {}) {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (res.status === 204) return null;
  if (!res.ok) {
    const detail = await res.text();
    throw new Error(detail || res.statusText);
  }
  return res.json();
}

/** @param {Record<string, unknown>} raw */
function mapInstance(raw) {
  return {
    id: /** @type {string} */ (raw.id),
    title: /** @type {string} */ (raw.title),
    createdAt: new Date(/** @type {string} */ (raw.created_at)).getTime(),
    updatedAt: new Date(/** @type {string} */ (raw.updated_at ?? raw.created_at)).getTime(),
    messages: Array.isArray(raw.messages)
      ? raw.messages.map((m) => ({
          id: m.id,
          role: m.role,
          text: m.text,
          created_at: m.created_at,
        }))
      : [],
    live_enabled: raw.live_enabled !== false,
    dataset_row_count: Number(raw.dataset_row_count) || 0,
    live_status: {},
  };
}

async function loadInstanceDetail(id) {
  const raw = await api(`/api/instances/${id}`);
  return mapInstance(raw);
}

async function refreshList() {
  const rows = await api("/api/instances");
  return rows.map((row) => mapInstance(row));
}

/** @param {Instance[]} summaries @param {Instance} detail */
function mergeInstances(summaries, detail) {
  const byId = new Map(summaries.map((i) => [i.id, { ...i, messages: [] }]));
  byId.set(detail.id, detail);
  return [...byId.values()].sort((a, b) => b.updatedAt - a.updatedAt);
}

export async function bootstrap() {
  let summaries = await refreshList();
  if (!summaries.length) {
    const created = mapInstance(await api("/api/instances", { method: "POST", body: "{}" }));
    summaries = [created];
  }

  let activeId = sessionStorage.getItem(ACTIVE_KEY) || summaries[0].id;
  if (!summaries.some((i) => i.id === activeId)) {
    activeId = summaries[0].id;
  }
  sessionStorage.setItem(ACTIVE_KEY, activeId);

  const detail = await loadInstanceDetail(activeId);
  commit({
    activeId,
    instances: mergeInstances(summaries, detail),
    ready: true,
  });
}

export async function createInstance() {
  const raw = await api("/api/instances", { method: "POST", body: "{}" });
  const detail = mapInstance(raw);
  sessionStorage.setItem(ACTIVE_KEY, detail.id);
  const summaries = await refreshList();
  commit({
    activeId: detail.id,
    instances: mergeInstances(summaries, detail),
  });
}

/** @param {string} id */
export async function setActiveInstance(id) {
  if (!state.instances.some((i) => i.id === id)) return;
  sessionStorage.setItem(ACTIVE_KEY, id);
  const detail = await loadInstanceDetail(id);
  commit({
    activeId: id,
    instances: state.instances.map((i) => (i.id === id ? detail : i)),
  });
}

/** @returns {Instance | undefined} */
export function getActiveInstance() {
  return state.instances.find((i) => i.id === state.activeId);
}

/** @param {string} userText */
export async function sendMessage(userText) {
  const active = getActiveInstance();
  if (!active) return;

  const optimistic = {
    ...active,
    messages: [
      ...active.messages,
      { id: Date.now(), role: "user", text: userText, created_at: new Date().toISOString() },
      {
        id: Date.now() + 1,
        role: "bot",
        text: "**Live on** — starting in background…",
        created_at: new Date().toISOString(),
      },
    ],
  };
  commit({
    instances: state.instances.map((i) => (i.id === active.id ? optimistic : i)),
  });

  const raw = await api(`/api/instances/${active.id}/messages`, {
    method: "POST",
    body: JSON.stringify({ text: userText }),
  });
  const detail = mapInstance(raw);
  const summaries = await refreshList();
  commit({
    instances: mergeInstances(summaries, detail),
  });
}

export async function refreshActiveInstance() {
  if (!state.activeId) return;
  const detail = await loadInstanceDetail(state.activeId);
  commit({
    instances: state.instances.map((i) => (i.id === detail.id ? detail : i)),
  });
}

/** @param {boolean} enabled */
export async function setLiveEnabled(enabled) {
  const active = getActiveInstance();
  if (!active) return;
  const raw = await api(`/api/instances/${active.id}/live`, {
    method: "PATCH",
    body: JSON.stringify({ enabled }),
  });
  const detail = mapInstance(raw);
  commit({
    instances: state.instances.map((i) => (i.id === detail.id ? detail : i)),
  });
}

/** @param {string} id */
export async function deleteInstance(id) {
  await api(`/api/instances/${id}`, { method: "DELETE" });
  let summaries = await refreshList();
  if (!summaries.length) {
    const created = mapInstance(await api("/api/instances", { method: "POST", body: "{}" }));
    summaries = [created];
  }

  let activeId = state.activeId;
  if (activeId === id || !summaries.some((i) => i.id === activeId)) {
    activeId = summaries[0].id;
  }
  sessionStorage.setItem(ACTIVE_KEY, activeId);
  const detail = await loadInstanceDetail(activeId);
  commit({
    activeId,
    instances: mergeInstances(summaries, detail),
  });
}
