/**
 * Claw-ED Student Chatbot Widget
 *
 * Self-contained, no-dependency JS widget that teachers paste into any webpage.
 * Use the embed snippet from the lesson page or `clawed export share --embed`.
 *
 * Optional attributes:
 *   data-lesson-id   — lesson ID to chat about
 *   data-share-token — lesson share token (required; never the teacher API token)
 *   data-teacher     — teacher name for header
 *   data-subject     — subject for header
 *   data-api-url     — base URL (default: script src origin)
 */
(function () {
    'use strict';

    // Find our script tag to read data attributes
    var scripts = document.getElementsByTagName('script');
    var thisScript = document.currentScript || scripts[scripts.length - 1];
    var lessonId = thisScript.getAttribute('data-lesson-id') || '';
    var shareToken = thisScript.getAttribute('data-share-token') || thisScript.getAttribute('data-token') || '';
    var conversationToken = null;
    var teacherName = thisScript.getAttribute('data-teacher') || 'Your Teacher';
    var subject = thisScript.getAttribute('data-subject') || '';
    var apiUrl = thisScript.getAttribute('data-api-url') || '';

    // Derive API base URL from script src if not explicitly set
    if (!apiUrl) {
        var src = thisScript.src || '';
        var idx = src.indexOf('/static/widget.js');
        apiUrl = idx !== -1 ? src.substring(0, idx) : '';
    }
    // Accept older snippets that supplied the full endpoint as the base URL.
    apiUrl = apiUrl.replace(/\/+$/, '').replace(/\/api\/chat(?:\/student)?$/, '');

    var headerText = 'Ask ' + teacherName + (subject ? ' about ' + subject : '');

    // Inject styles (scoped to our widget)
    var style = document.createElement('style');
    style.textContent = [
        '#clawed-widget-btn{',
        '  position:fixed;bottom:20px;right:20px;z-index:99999;',
        '  width:56px;height:56px;border-radius:50%;border:none;',
        '  background:#1a56db;color:#fff;font-size:24px;cursor:pointer;',
        '  box-shadow:0 4px 12px rgba(0,0,0,0.25);transition:transform 0.2s;',
        '  display:flex;align-items:center;justify-content:center;',
        '  font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;',
        '}',
        '#clawed-widget-btn:hover{transform:scale(1.08);}',
        '#clawed-widget-panel{',
        '  position:fixed;bottom:86px;right:20px;z-index:99999;',
        '  width:360px;max-height:500px;border-radius:12px;',
        '  background:#fff;box-shadow:0 8px 30px rgba(0,0,0,0.18);',
        '  display:none;flex-direction:column;overflow:hidden;',
        '  font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;',
        '  font-size:14px;color:#1a1a2e;line-height:1.5;',
        '}',
        '#clawed-widget-panel.open{display:flex;}',
        '#clawed-header{',
        '  background:#0f3460;color:#fff;padding:14px 16px;',
        '  font-weight:600;font-size:14px;display:flex;',
        '  align-items:center;justify-content:space-between;',
        '}',
        '#clawed-header button{',
        '  background:none;border:none;color:rgba(255,255,255,0.7);',
        '  font-size:18px;cursor:pointer;padding:0 4px;',
        '}',
        '#clawed-header button:hover{color:#fff;}',
        '#clawed-messages{',
        '  flex:1;overflow-y:auto;padding:12px;min-height:200px;max-height:340px;',
        '  background:#f9fafb;',
        '}',
        '.clawed-msg{',
        '  padding:8px 12px;margin-bottom:8px;border-radius:8px;',
        '  max-width:85%;word-wrap:break-word;font-size:13px;',
        '}',
        '.clawed-msg.user{',
        '  background:#e8f0fe;margin-left:auto;text-align:right;',
        '}',
        '.clawed-msg.assistant{',
        '  background:#fff;border:1px solid #e5e7eb;margin-right:auto;',
        '}',
        '.clawed-msg.typing{',
        '  background:#fff;border:1px solid #e5e7eb;margin-right:auto;',
        '  color:#6b7280;font-style:italic;',
        '}',
        '#clawed-input-row{',
        '  display:flex;padding:10px;border-top:1px solid #e5e7eb;background:#fff;',
        '}',
        '#clawed-input{',
        '  flex:1;padding:8px 12px;border:1px solid #d1d5db;border-radius:8px;',
        '  font-size:13px;font-family:inherit;outline:none;',
        '}',
        '#clawed-input:focus{border-color:#1a56db;box-shadow:0 0 0 2px rgba(26,86,219,0.1);}',
        '#clawed-send{',
        '  margin-left:8px;padding:8px 14px;border:none;border-radius:8px;',
        '  background:#1a56db;color:#fff;font-size:13px;cursor:pointer;',
        '  font-weight:500;',
        '}',
        '#clawed-send:hover{background:#1e40af;}',
        '#clawed-send:disabled{opacity:0.5;cursor:not-allowed;}',
    ].join('\n');
    document.head.appendChild(style);

    // Create widget button
    var btn = document.createElement('button');
    btn.id = 'clawed-widget-btn';
    btn.innerHTML = '&#128172;';
    btn.title = 'Chat with your teacher';
    document.body.appendChild(btn);

    // Create chat panel
    var panel = document.createElement('div');
    panel.id = 'clawed-widget-panel';
    panel.innerHTML = [
        '<div id="clawed-header">',
        '  <span>' + escHtml(headerText) + '</span>',
        '  <button id="clawed-close" title="Close">&times;</button>',
        '</div>',
        '<div id="clawed-messages"></div>',
        '<div id="clawed-input-row">',
        '  <input type="text" id="clawed-input" placeholder="Ask a question..." autocomplete="off">',
        '  <button id="clawed-send">Send</button>',
        '</div>',
    ].join('\n');
    document.body.appendChild(panel);

    // Toggle panel
    btn.addEventListener('click', function () {
        panel.classList.toggle('open');
        if (panel.classList.contains('open')) {
            document.getElementById('clawed-input').focus();
        }
    });

    document.getElementById('clawed-close').addEventListener('click', function () {
        panel.classList.remove('open');
    });

    // Send message
    var input = document.getElementById('clawed-input');
    var sendBtn = document.getElementById('clawed-send');
    var messages = document.getElementById('clawed-messages');

    function sendMessage() {
        var question = input.value.trim();
        if (!question || sendBtn.disabled) return;
        if (!lessonId || !shareToken) {
            appendMsg('assistant', 'This chat link is incomplete. Ask your teacher for a new embed link.');
            return;
        }

        appendMsg('user', question);
        input.value = '';
        sendBtn.disabled = true;

        // Show typing indicator
        var typing = appendMsg('typing', 'Thinking...');

        var xhr = new XMLHttpRequest();
        xhr.open('POST', apiUrl + '/api/chat/student', true);
        xhr.setRequestHeader('Content-Type', 'application/json');
        xhr.onreadystatechange = function () {
            if (xhr.readyState !== 4) return;
            // Remove typing indicator
            if (typing && typing.parentNode) typing.parentNode.removeChild(typing);
            sendBtn.disabled = false;

            if (xhr.status === 200) {
                try {
                    var data = JSON.parse(xhr.responseText);
                    conversationToken = data.conversation_token || conversationToken;
                    appendMsg('assistant', data.response || data.error || 'No response');
                } catch (e) {
                    appendMsg('assistant', 'Error parsing response.');
                }
            } else {
                appendMsg('assistant', 'Error: could not reach the server.');
            }
        };
        xhr.send(JSON.stringify({
            lesson_id: lessonId, share_token: shareToken,
            question: question, conversation_token: conversationToken
        }));
    }

    sendBtn.addEventListener('click', sendMessage);
    input.addEventListener('keydown', function (e) {
        if (e.key === 'Enter') {
            e.preventDefault();
            sendMessage();
        }
    });

    function appendMsg(role, text) {
        var div = document.createElement('div');
        div.className = 'clawed-msg ' + role;
        div.textContent = text;
        messages.appendChild(div);
        messages.scrollTop = messages.scrollHeight;
        return div;
    }

    function escHtml(s) {
        var d = document.createElement('div');
        d.textContent = s;
        return d.innerHTML;
    }
})();
