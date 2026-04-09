/**
 * Claw-ED Chrome Extension — Background Service Worker
 *
 * Creates a right-click context menu: "Generate Lesson from Selection"
 * Sends highlighted text to the local Claw-ED API server.
 */

const CLAWED_API = "http://localhost:8000";

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
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          text: selectedText,
          source_url: tab.url,
          source_title: tab.title,
          action: "generate_lesson",
        }),
      });

      if (response.ok) {
        const data = await response.json();
        // Send result to content script for display
        chrome.tabs.sendMessage(tab.id, {
          type: "clawed-result",
          data: data,
        });
      } else {
        chrome.tabs.sendMessage(tab.id, {
          type: "clawed-error",
          message: "Claw-ED server not responding. Run: clawed serve",
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
      await fetch(`${CLAWED_API}/api/extension/add-source`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          text: selectedText,
          source_url: tab.url,
          source_title: tab.title,
        }),
      });
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
