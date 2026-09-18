// Execute the real widget script against a minimal DOM and XHR transport.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const source = fs.readFileSync(path.join(__dirname, '../clawed/api/static/widget.js'), 'utf8');

function runWidget(apiUrl, shareToken = 'lesson-share-token') {
    const elements = {};
    function element() {
        return {
            value: '', disabled: false, handlers: {},
            appendChild(child) { child.parentNode = this; }, removeChild() {},
            addEventListener(event, callback) { this.handlers[event] = callback; },
            classList: { toggle() {}, contains() { return true; }, remove() {} }, focus() {},
        };
    }
    const attributes = { 'data-lesson-id': 'lesson-1', 'data-share-token': shareToken, 'data-api-url': apiUrl };
    const script = { src: 'https://teacher.example/static/widget.js', getAttribute(name) { return attributes[name]; } };
    const requests = [];
    class XHR {
        open(method, url) { this.method = method; this.url = url; }
        setRequestHeader() {}
        send(body) { this.body = JSON.parse(body); requests.push(this); }
    }
    const document = {
        currentScript: script,
        // A later unrelated script must not change the widget's configuration.
        getElementsByTagName() { return [script, { getAttribute() { return 'wrong'; } }]; },
        createElement: element, head: element(), body: element(),
        getElementById(id) { return elements[id] ||= element(); },
    };
    vm.runInNewContext(source, { document, XMLHttpRequest: XHR });
    function send(question) {
        elements['clawed-input'].value = question;
        elements['clawed-send'].handlers.click();
    }
    send('First question');
    if (!shareToken) { assert.equal(requests.length, 0); return; }
    assert.equal(requests.length, 1);
    assert.equal(requests[0].url, 'https://teacher.example/api/chat/student');
    assert.equal(requests[0].body.share_token, shareToken);
    assert.equal(requests[0].body.lesson_id, 'lesson-1');
    assert.equal(requests[0].body.conversation_token, null);
    send('Duplicate while pending');
    assert.equal(requests.length, 1);
    Object.assign(requests[0], { readyState: 4, status: 200,
        responseText: JSON.stringify({ response: 'Answer', conversation_token: 'opaque-session-token' }) });
    requests[0].onreadystatechange();
    send('Follow-up');
    assert.equal(requests[1].body.conversation_token, 'opaque-session-token');
}
runWidget('https://teacher.example');
runWidget('https://teacher.example/');
runWidget('https://teacher.example/api/chat/student');
runWidget('');
runWidget('https://teacher.example', '');
