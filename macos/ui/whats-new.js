(() => {
 "use strict";
 const dialog = document.getElementById("release-highlights");
 const trigger = document.getElementById("workspace-version");
 let data = null, attempted = false, interrupted = false, origin = null;
 document.addEventListener("pointerdown", () => { interrupted = true; }, true);
 document.addEventListener("keydown", () => { interrupted = true; }, true);
 const open = () => {
  if (!data?.items?.length || dialog.open) return;
  origin = document.activeElement;
  document.getElementById("release-version").textContent = `AI一手工具箱 · v${data.release}`;
  document.getElementById("release-heading").textContent = data.title;
  document.getElementById("release-description").textContent = data.description;
  const rows = document.getElementById("release-items"); rows.replaceChildren();
  for (const item of data.items) {
   const row = document.createElement("section"); row.className = "release-item";
   const title = document.createElement("h3"), badge = document.createElement("span"), label = document.createElement("span"), text = document.createElement("p");
   badge.className = "release-label"; badge.textContent = item.label; label.textContent = item.title; text.textContent = item.text;
   title.append(badge, label); row.append(title, text); rows.append(row);
  }
  dialog.showModal(); document.getElementById("release-done").focus();
 };
 const dismiss = () => dialog.close();
 dialog.addEventListener("keydown", event => {
  if (event.key !== "Tab") return;
  const buttons = [...dialog.querySelectorAll("button:not(:disabled)")];
  const target = event.shiftKey ? buttons.at(-1) : buttons[0];
  if (document.activeElement === (event.shiftKey ? buttons[0] : buttons.at(-1))) { event.preventDefault(); target.focus(); }
 });
 dialog.addEventListener("close", () => {
  if (data) { data.automatic = false; Promise.resolve(window.pywebview?.api?.acknowledge_release_notes?.(data.release)).catch(() => {}); }
  if (origin instanceof HTMLElement && origin !== document.body) origin.focus();
  else trigger.focus();
 });
 document.getElementById("release-close").addEventListener("click", dismiss);
 document.getElementById("release-done").addEventListener("click", dismiss);
 document.getElementById("release-full").addEventListener("click", () => Promise.resolve(window.pywebview?.api?.open_release_notes?.()).catch(() => {}));
 trigger.addEventListener("click", async () => {
  if (!data) { try { data = await window.pywebview?.api?.release_notes?.(); } catch {} }
  open();
 });
 window.aiFirstReleaseNotesReady = async automatic => {
  try { data = await window.pywebview?.api?.release_notes?.(); } catch { return; }
  if (attempted || !automatic || !data?.automatic) return;
  attempted = true;
  setTimeout(() => {
   if (!data?.automatic || document.visibilityState === "hidden" || !document.hasFocus() || interrupted || document.querySelector(".sheet:not([hidden]), dialog[open]")) return;
   open();
  }, 650);
 };
})();
