/**
 * Claw-ED Content Script — displays results in a floating panel
 */

chrome.runtime.onMessage.addListener((msg) => {
  if (msg.type === "clawed-result") {
    showPanel(msg.data);
  }
  if (msg.type === "clawed-error") {
    showPanel({ error: msg.message });
  }
});

function showPanel(data) {
  // Remove existing panel
  const existing = document.getElementById("clawed-panel");
  if (existing) existing.remove();

  const panel = document.createElement("div");
  panel.id = "clawed-panel";

  if (data.error) {
    panel.innerHTML = `
      <div class="clawed-header">
        <span>Claw-ED</span>
        <button onclick="this.parentElement.parentElement.remove()">&times;</button>
      </div>
      <div class="clawed-body clawed-error">${data.error}</div>
    `;
  } else if (data.message) {
    panel.innerHTML = `
      <div class="clawed-header">
        <span>Claw-ED</span>
        <button onclick="this.parentElement.parentElement.remove()">&times;</button>
      </div>
      <div class="clawed-body">${data.message}</div>
    `;
  } else {
    const title = data.title || "Lesson Generated";
    const files = (data.files || []).map(f => `<li>${f}</li>`).join("");
    panel.innerHTML = `
      <div class="clawed-header">
        <span>Claw-ED</span>
        <button onclick="this.parentElement.parentElement.remove()">&times;</button>
      </div>
      <div class="clawed-body">
        <h3>${title}</h3>
        ${data.objective ? `<p><strong>Objective:</strong> ${data.objective}</p>` : ""}
        ${files ? `<p><strong>Files:</strong></p><ul>${files}</ul>` : ""}
        <p><a href="http://localhost:8000" target="_blank">Open Claw-ED Dashboard</a></p>
      </div>
    `;
  }

  document.body.appendChild(panel);

  // Auto-dismiss after 15 seconds
  setTimeout(() => {
    const el = document.getElementById("clawed-panel");
    if (el) el.remove();
  }, 15000);
}
