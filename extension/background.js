/**
 * Claw-ED Chrome Extension — Background Service Worker
 *
 * Creates a right-click context menu: "Generate Lesson from Selection"
 * Sends highlighted text to the local Claw-ED API server with auth.
 */

// API URL — configurable via chrome.storage. Defaults to localhost.
let CLAWED_API = "http://localhost:8000";
let CLAWED_TOKEN = "";

// Load config from storage
chrome.storage.sync.get(["apiUrl", "apiToken"], (data) => {
  if (data.apiUrl) CLAWED_API = data.apiUrl;
  if (data.apiToken) CLAWED_TOKEN = data.apiToken;
});

// Listen for config changes
chrome.storage.onChanged.addListener((changes) => {
  if (changes.apiUrl) CLAWED_API = changes.apiUrl.newValue || CLAWED_API;
  if (changes.apiToken) CLAWED_TOKEN = changes.apiToken.newValue || "";
});

function getHeaders() {
  const headers = { "Content-Type": "application/json" };
  if (CLAWED_TOKEN) {
    headers["Authorization"] = `Bearer ${CLAWED_TOKEN}`;
  }
  return headers;
}

// Create context menu on install
chrome.runtime.onInstalled.addListener(() => {
  chrome.contextMenus.create({
    id: "clawed-generate",
    title: "Generate Lesson from Selection",
    contexts: ["selection"],
  });
  chrome.contextMenus.create({
    id: "clawed-source",
    title: "Use as Primary Source",
    contexts: ["selection"],
  });
});

// Handle context menu clicks
chrome.contextMenus.onClicked.addListener(async (info, tab) => {
  const selectedText = info.selectionText;
  if (!selectedText) return;

  if (info.menuItemId === "clawed-generate") {
    try {
      const response = await fetch(`${CLAWED_API}/api/extension/generate`, {
        method: "POST",
        headers: getHeaders(),
        body: JSON.stringify({
          text: selectedText,
          source_url: tab.url,
          source_title: tab.title,
          action: "generate_lesson",
        }),
      });

      if (response.status === 401) {
        chrome.tabs.sendMessage(tab.id, {
          type: "clawed-error",
          message: "Authentication required. Open the Claw-ED extension popup and enter your API token.",
        });
        return;
      }

      if (response.ok) {
        const data = await response.json();
        chrome.tabs.sendMessage(tab.id, {
          type: "clawed-result",
          data: data,
        });
      } else {
        chrome.tabs.sendMessage(tab.id, {
          type: "clawed-error",
          message: "Claw-ED server error. Run: clawed serve",
        });
      }
    } catch (err) {
      chrome.tabs.sendMessage(tab.id, {
        type: "clawed-error",
        message: "Cannot connect to Claw-ED. Start the server with: clawed serve",
      });
    }
  }

  if (info.menuItemId === "clawed-source") {
    try {
      const response = await fetch(`${CLAWED_API}/api/extension/add-source`, {
        method: "POST",
        headers: getHeaders(),
        body: JSON.stringify({
          text: selectedText,
          source_url: tab.url,
          source_title: tab.title,
        }),
      });

      if (response.status === 401) {
        chrome.tabs.sendMessage(tab.id, {
          type: "clawed-error",
          message: "Authentication required. Configure your API token in the extension popup.",
        });
        return;
      }

      chrome.tabs.sendMessage(tab.id, {
        type: "clawed-result",
        data: { message: "Source saved! Use it in your next lesson." },
      });
    } catch (err) {
      chrome.tabs.sendMessage(tab.id, {
        type: "clawed-error",
        message: "Cannot connect to Claw-ED.",
      });
    }
  }
});
