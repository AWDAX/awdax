import { getActiveInstance, sendMessage, subscribe } from "./store.js";
import { renderMarkdown } from "./markdown.js";

/** @param {HTMLElement} root */
export function mountChat(root) {
  const form = document.getElementById("chat-form");
  const input = /** @type {HTMLInputElement | null} */ (
    document.getElementById("chat-input")
  );
  if (!form || !input) return;

  subscribe((state) => {
    if (!state.ready) {
      root.innerHTML = '<p class="chat-placeholder">Loading…</p>';
      return;
    }
    renderMessages(root, getActiveInstance()?.messages ?? []);
  });

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const text = input.value.trim();
    if (!text) return;
    input.value = "";
    input.disabled = true;
    try {
      await sendMessage(text);
    } catch (err) {
      console.error(err);
      appendMessageEl(root, "Something went wrong. Try again.", "bot");
    } finally {
      input.disabled = false;
      input.focus();
    }
  });
}

/** @param {HTMLElement} root @param {import("./store.js").Instance["messages"]} messages */
function renderMessages(root, messages) {
  root.innerHTML = "";
  if (!messages.length) {
    root.innerHTML = '<p class="chat-placeholder">Describe what you want to track.</p>';
    return;
  }
  for (const msg of messages) {
    appendMessageEl(root, msg.text, msg.role);
  }
  root.scrollTop = root.scrollHeight;
}

/** @param {HTMLElement} root @param {string} text @param {"user"|"bot"} role */
function appendMessageEl(root, text, role) {
  const el = document.createElement("div");
  el.className = `msg msg-${role}`;
  if (role === "bot") {
    el.classList.add("msg-markdown");
    el.innerHTML = renderMarkdown(text);
  } else {
    el.textContent = text;
  }
  root.appendChild(el);
  root.scrollTop = root.scrollHeight;
}
