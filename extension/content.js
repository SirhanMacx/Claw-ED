/**
 * Claw-ED Content Script — displays results in a floating panel.
 * XSS-safe: uses textContent and DOM creation, never innerHTML with user data.
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

  // Header (static — safe)
  const header = document.createElement("div");
  header.className = "clawed-header";
  const headerText = document.createElement("span");
  headerText.textContent = "Claw-ED";
  const closeBtn = document.createElement("button");
  closeBtn.textContent = "\u00d7";
  closeBtn.addEventListener("click", () => panel.remove());
  header.appendChild(headerText);
  header.appendChild(closeBtn);
  panel.appendChild(header);

  // Body
  const body = document.createElement("div");
  body.className = "clawed-body";

  if (data.error) {
    body.className += " clawed-error";
    body.textContent = data.error;
  } else if (data.message) {
    body.textContent = data.message;
  } else {
    const title = document.createElement("h3");
    title.textContent = data.title || "Lesson Generated";
    body.appendChild(title);

    if (data.objective) {
      const obj = document.createElement("p");
      const strong = document.createElement("strong");
      strong.textContent = "Objective: ";
      obj.appendChild(strong);
      obj.appendChild(document.createTextNode(data.objective));
      body.appendChild(obj);
    }

    if (data.files && data.files.length > 0) {
      const filesLabel = document.createElement("p");
      const filesStrong = document.createElement("strong");
      filesStrong.textContent = "Files:";
      filesLabel.appendChild(filesStrong);
      body.appendChild(filesLabel);
      const ul = document.createElement("ul");
      data.files.forEach((f) => {
        const li = document.createElement("li");
        li.textContent = f;
        ul.appendChild(li);
      });
      body.appendChild(ul);
    }

    const link = document.createElement("p");
    const a = document.createElement("a");
    a.href = "http://localhost:8000";
    a.target = "_blank";
    a.textContent = "Open Claw-ED Dashboard";
    link.appendChild(a);
    body.appendChild(link);
  }

  panel.appendChild(body);
  document.body.appendChild(panel);

  // Auto-dismiss after 15 seconds
  setTimeout(() => {
    const el = document.getElementById("clawed-panel");
    if (el) el.remove();
  }, 15000);
}
