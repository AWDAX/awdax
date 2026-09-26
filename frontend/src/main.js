import { bootstrap } from "./store.js";
import { mountChat } from "./chat.js";
import { mountSidebar } from "./sidebar.js";
import { mountLiveStatus } from "./live/status.js";
import { mountDashboard } from "./dashboard/index.js";

try {
  await bootstrap();
} catch (err) {
  console.error("Failed to load instances:", err);
}

mountSidebar(document.getElementById("sidebar"));
mountChat(document.getElementById("chat-messages"));
mountLiveStatus(document.getElementById("live-status"));
mountDashboard(document.getElementById("dashboard"));
