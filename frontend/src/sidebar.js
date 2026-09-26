import { createInstance, deleteInstance, setActiveInstance, subscribe } from "./store.js";

/** @param {HTMLElement} root */
export function mountSidebar(root) {
  root.innerHTML = `
    <div class="sidebar-top">
      <span class="sidebar-brand">AWDAX</span>
      <button type="button" class="sidebar-new" id="new-instance">+ New</button>
    </div>
    <ul class="sidebar-list" id="instance-list"></ul>
  `;

  const list = /** @type {HTMLElement} */ (root.querySelector("#instance-list"));
  const newBtn = /** @type {HTMLButtonElement} */ (root.querySelector("#new-instance"));

  newBtn.addEventListener("click", () => {
    newBtn.disabled = true;
    createInstance()
      .catch(console.error)
      .finally(() => {
        newBtn.disabled = false;
      });
  });

  subscribe((state) => {
    list.innerHTML = "";
    if (!state.ready) {
      list.innerHTML = '<li class="sidebar-empty">Loading…</li>';
      return;
    }
    for (const instance of state.instances) {
      const li = document.createElement("li");
      li.className = "sidebar-row";

      const btn = document.createElement("button");
      btn.type = "button";
      btn.className =
        instance.id === state.activeId
          ? "sidebar-item is-active"
          : "sidebar-item";
      btn.textContent = instance.title;
      btn.title = instance.title;
      btn.addEventListener("click", () => {
        setActiveInstance(instance.id).catch(console.error);
      });

      const del = document.createElement("button");
      del.type = "button";
      del.className = "sidebar-delete";
      del.setAttribute("aria-label", "Delete track");
      del.textContent = "×";
      del.addEventListener("click", (e) => {
        e.stopPropagation();
        if (state.instances.length === 1) {
          if (!confirm("Delete this track? A new empty one will be created.")) return;
        } else if (!confirm(`Delete "${instance.title}"?`)) {
          return;
        }
        deleteInstance(instance.id).catch(console.error);
      });

      li.appendChild(btn);
      li.appendChild(del);
      list.appendChild(li);
    }
  });
}
