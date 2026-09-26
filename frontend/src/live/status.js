import {
  getActiveInstance,
  getState,
  setLiveEnabled,
  subscribe,
  refreshActiveInstance,
} from "../store.js";

/** @param {HTMLElement} root */
export function mountLiveStatus(root) {
  root.innerHTML = `
    <div class="live-bar">
      <button type="button" class="live-toggle is-on" id="live-toggle" aria-pressed="true">
        <span class="live-dot" aria-hidden="true"></span>
        Live
      </button>
      <div class="live-copy">
        <div class="live-phase" id="live-phase">Idle</div>
        <div class="live-detail" id="live-detail">Turn on a track with a goal to start fetching.</div>
      </div>
      <div class="live-meta" id="live-meta"></div>
    </div>
  `;

  const toggle = /** @type {HTMLButtonElement} */ (root.querySelector("#live-toggle"));
  const phaseEl = /** @type {HTMLElement} */ (root.querySelector("#live-phase"));
  const detailEl = /** @type {HTMLElement} */ (root.querySelector("#live-detail"));
  const metaEl = /** @type {HTMLElement} */ (root.querySelector("#live-meta"));

  /** @type {EventSource | null} */
  let stream = null;
  /** @type {string} */
  let streamForInstance = "";
  /** @type {ReturnType<typeof setTimeout> | null} */
  let reconnectTimer = null;
  /** @type {ReturnType<typeof setTimeout> | null} */
  let chatRefreshTimer = null;

  function closeStream() {
    if (reconnectTimer) {
      clearTimeout(reconnectTimer);
      reconnectTimer = null;
    }
    if (stream) {
      stream.close();
      stream = null;
    }
    streamForInstance = "";
  }

  function applyPayload(payload) {
    const enabled = payload.live_enabled !== false;
    toggle.classList.toggle("is-on", enabled);
    toggle.setAttribute("aria-pressed", enabled ? "true" : "false");
    const st = payload.status || {};
    const phase = st.phase || "idle";
    phaseEl.textContent = phase.charAt(0).toUpperCase() + phase.slice(1);
    detailEl.textContent =
      st.detail ||
      (st.current_source ? `Fetching ${st.current_source}` : "Waiting for next cycle…");
    const rows = payload.rows_total ?? st.rows_total ?? 0;
    const added = st.rows_added_last_cycle;
    metaEl.textContent =
      added != null && added > 0
        ? `${rows} rows · +${added} this cycle`
        : `${rows} rows`;
  }

  function scheduleChatRefresh() {
    if (chatRefreshTimer) return;
    chatRefreshTimer = setTimeout(() => {
      chatRefreshTimer = null;
      refreshActiveInstance().catch(() => {});
    }, 800);
  }

  function connectStream(instanceId) {
    if (!instanceId || streamForInstance === instanceId) return;
    closeStream();
    streamForInstance = instanceId;
    stream = new EventSource(`/api/instances/${instanceId}/live/stream`);
    stream.onmessage = (ev) => {
      try {
        const payload = JSON.parse(ev.data);
        applyPayload(payload);
        if (payload.dataset) {
          document.dispatchEvent(
            new CustomEvent("awdax:dataset", { detail: payload.dataset })
          );
        }
        if (payload.chat_updated) {
          scheduleChatRefresh();
        }
      } catch {
        /* ignore keepalive / parse errors */
      }
    };
    stream.onerror = () => {
      if (!stream || streamForInstance !== instanceId) return;
      closeStream();
      reconnectTimer = setTimeout(() => {
        if (getState().activeId === instanceId) {
          connectStream(instanceId);
        }
      }, 5000);
    };
  }

  toggle.addEventListener("click", () => {
    const active = getActiveInstance();
    if (!active) return;
    const next = !toggle.classList.contains("is-on");
    toggle.disabled = true;
    setLiveEnabled(next)
      .catch(console.error)
      .finally(() => {
        toggle.disabled = false;
      });
  });

  /** @type {string} */
  let lastActiveId = "";

  subscribe((state) => {
    if (!state.ready) return;
    const active = state.instances.find((i) => i.id === state.activeId);
    if (!active) return;
    applyPayload({
      live_enabled: active.live_enabled,
      rows_total: active.dataset_row_count,
      status: active.live_status || {},
    });
    if (state.activeId !== lastActiveId) {
      lastActiveId = state.activeId;
      connectStream(state.activeId);
    }
  });
}
