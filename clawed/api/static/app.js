/* Claw-ED — JS for dark mode, wizard, settings, form handling, SSE, chat, feedback. */

document.addEventListener('DOMContentLoaded', function () {

    // ── Dark Mode Toggle ─────────────────────────────────────────────
    var darkToggle = document.getElementById('dark-toggle');
    if (darkToggle) {
        // Set initial icon
        var isDark = document.documentElement.getAttribute('data-theme') === 'dark';
        darkToggle.textContent = isDark ? '\u2600' : '\u263E';

        darkToggle.addEventListener('click', function () {
            var html = document.documentElement;
            var current = html.getAttribute('data-theme');
            if (current === 'dark') {
                html.removeAttribute('data-theme');
                localStorage.setItem('clawed-theme', 'light');
                darkToggle.textContent = '\u263E';
            } else {
                html.setAttribute('data-theme', 'dark');
                localStorage.setItem('clawed-theme', 'dark');
                darkToggle.textContent = '\u2600';
            }
        });
    }

    // ── Toast Notifications ──────────────────────────────────────────
    var toastEl = document.getElementById('toast');
    window.eduToast = function (msg, type) {
        if (!toastEl) return;
        toastEl.textContent = msg;
        toastEl.className = 'toast visible' + (type ? ' toast-' + type : '');
        clearTimeout(toastEl._timer);
        toastEl._timer = setTimeout(function () {
            toastEl.className = 'toast';
        }, 3000);
    };

    // ── Notification Badge ───────────────────────────────────────────
    var notifyBadge = document.getElementById('notify-badge');
    var notifyCount = 0;
    window.eduNotify = function () {
        notifyCount++;
        if (notifyBadge) {
            notifyBadge.textContent = notifyCount;
            notifyBadge.classList.add('visible');
        }
    };
    // Clear badge when clicking analytics
    if (notifyBadge) {
        var analyticsLink = notifyBadge.parentElement.querySelector('a');
        if (analyticsLink) {
            analyticsLink.addEventListener('click', function () {
                notifyCount = 0;
                notifyBadge.classList.remove('visible');
            });
        }
    }

    // ── Hamburger Menu ───────────────────────────────────────────────
    var hamburger = document.getElementById('nav-hamburger');
    var navLinks = document.getElementById('nav-links');
    if (hamburger && navLinks) {
        hamburger.addEventListener('click', function () {
            navLinks.classList.toggle('open');
        });
    }

    // ── Health Check (Status Bar) ────────────────────────────────────
    var statusDot = document.getElementById('status-dot');
    var statusText = document.getElementById('status-text');
    if (statusDot && statusText) {
        fetch('/api/health').then(function (r) { return r.json(); }).then(function (data) {
            if (data.llm_connected) {
                statusDot.className = 'status-dot connected';
                statusText.textContent = 'Connected';
                // Keep the model slug for power users, but off the teacher's screen.
                statusText.title = data.llm_model ? ('Model: ' + data.llm_model) : '';
            } else {
                statusDot.className = 'status-dot disconnected';
                statusText.textContent = 'Not connected \u2014 add a key in Settings';
            }
        }).catch(function () {
            statusDot.className = 'status-dot disconnected';
            statusText.textContent = 'Could not reach server';
        });
    }

    // ── Onboarding Wizard ────────────────────────────────────────────
    var wizard = document.getElementById('wizard');
    var wizardState = { teacherId: null, persona: null, unitId: null, lessonId: null };

    if (wizard) {
        var stepIndicators = wizard.querySelectorAll('.wizard-step');
        var panels = wizard.querySelectorAll('.wizard-panel');

        function goToStep(stepId) {
            panels.forEach(function (p) { p.classList.remove('active'); });
            var target = document.getElementById(stepId);
            if (target) target.classList.add('active');

            // Prefer an explicit data-indicator on the panel (decouples panel
            // ids from the numbered progress bar). Fall back to parsing the id
            // for any panel that predates the attribute.
            var stepNum;
            if (target && target.dataset.indicator) {
                stepNum = parseInt(target.dataset.indicator);
            } else {
                stepNum = parseInt(stepId.replace('step-', '').replace('a', '').replace('b', ''));
            }
            stepIndicators.forEach(function (s) {
                var sNum = parseInt(s.dataset.step);
                s.classList.remove('active');
                s.classList.remove('completed');
                if (sNum < stepNum) s.classList.add('completed');
                if (sNum === stepNum) s.classList.add('active');
            });
            // Keep the wizard in view when advancing on small screens.
            if (target && typeof target.scrollIntoView === 'function') {
                try { window.scrollTo({ top: 0, behavior: 'smooth' }); } catch (e) { window.scrollTo(0, 0); }
            }
        }

        // Step 1: Path selection. We remember which setup path the teacher
        // picked, route them through the new "Connect your AI" step first, then
        // continue to their chosen path (upload vs. quick form).
        var pathUpload = document.getElementById('path-upload');
        var pathScratch = document.getElementById('path-scratch');
        wizardState.setupPath = 'step-2b';
        if (pathUpload) pathUpload.addEventListener('click', function () {
            wizardState.setupPath = 'step-2a';
            enterConnectStep();
        });
        if (pathScratch) pathScratch.addEventListener('click', function () {
            wizardState.setupPath = 'step-2b';
            enterConnectStep();
        });

        // ── Step 2: Connect your AI ──────────────────────────────────
        // Backend does the heavy lifting: /api/onboarding/detect surfaces a
        // ready provider (local Ollama or an already-configured key); the
        // teacher clicks "Use it", or picks a provider, pastes a key, and we
        // POST /api/settings then GET /api/settings/test-connection. On success
        // the app is fully configured — no tier/other config required.
        var PROVIDER_LABELS = {
            anthropic: 'Anthropic (Claude)',
            openai: 'OpenAI',
            ollama: 'Ollama',
            openrouter: 'OpenRouter',
            google: 'Google Gemini'
        };
        var DEFAULT_MODELS = {
            anthropic: 'claude-sonnet-4-6',
            openai: 'gpt-4.1',
            ollama: '',
            openrouter: 'nvidia/nemotron-3-super-120b-a12b:free',
            google: 'gemini-2.5-flash'
        };

        var connDetecting = document.getElementById('connect-detecting');
        var connDetected = document.getElementById('connect-detected');
        var connDetectedLabel = document.getElementById('connect-detected-label');
        var connDetectedNote = document.getElementById('connect-detected-note');
        var connDetectedStatus = document.getElementById('connect-detected-status');
        var connUseDetected = document.getElementById('connect-use-detected');
        var connShowChooser = document.getElementById('connect-show-chooser');
        var connChooser = document.getElementById('connect-chooser');
        var connCards = document.getElementById('connect-cards');
        var connFormWrap = document.getElementById('connect-form-wrap');
        var connStatus = document.getElementById('connect-status');
        var connSubmit = document.getElementById('connect-submit');
        var connSuccess = document.getElementById('connect-success');
        var connSuccessTitle = document.getElementById('connect-success-title');
        var connContinue = document.getElementById('connect-continue');
        var connReconnect = document.getElementById('connect-reconnect');

        var connectState = { detected: null, selected: null, baseSettings: null, detectLoaded: false };

        function show(el) { if (el) el.hidden = false; }
        function hide(el) { if (el) el.hidden = true; }

        // Fetch current settings once so we can preserve unrelated fields
        // (models for other providers, ollama url) when we POST our change.
        function loadBaseSettings() {
            return fetch('/api/settings')
                .then(function (r) { return r.json(); })
                .then(function (s) { connectState.baseSettings = s || {}; return connectState.baseSettings; })
                .catch(function () { connectState.baseSettings = {}; return connectState.baseSettings; });
        }

        function enterConnectStep() {
            goToStep('step-connect');
            loadBaseSettings();
            if (!connectState.detectLoaded) {
                connectState.detectLoaded = true;
                runDetect();
            }
        }

        function runDetect() {
            show(connDetecting);
            hide(connDetected);
            hide(connChooser);
            hide(connSuccess);
            fetch('/api/onboarding/detect')
                .then(function (r) { return r.json(); })
                .then(function (data) {
                    hide(connDetecting);
                    var list = (data && data.detected) || [];
                    if (data && data.any && list.length) {
                        // Prefer the first ready provider; Ollama (local) sorts
                        // first from the backend, then configured keys.
                        var pick = null;
                        for (var i = 0; i < list.length; i++) {
                            if (list[i].ready) { pick = list[i]; break; }
                        }
                        if (!pick) pick = list[0];
                        connectState.detected = pick;
                        if (connDetectedLabel) connDetectedLabel.textContent = 'We found ' + (pick.label || PROVIDER_LABELS[pick.provider] || pick.provider) + ' on your machine';
                        if (connDetectedNote) connDetectedNote.textContent = pick.note || 'Ready to use.';
                        show(connDetected);
                    } else {
                        // Nothing ready — go straight to the chooser.
                        showChooser();
                    }
                })
                .catch(function () {
                    hide(connDetecting);
                    showChooser();
                });
        }

        function showChooser() {
            hide(connDetected);
            hide(connSuccess);
            show(connChooser);
        }

        function defaultModelFor(prov) {
            // Use a detected Ollama model if we have one; else the recommended default.
            if (prov === 'ollama' && connectState.detected &&
                connectState.detected.provider === 'ollama' &&
                connectState.detected.models && connectState.detected.models.length) {
                return connectState.detected.models[0];
            }
            return DEFAULT_MODELS[prov] || '';
        }

        // "Use it & continue" — save the detected provider as-is and continue.
        if (connUseDetected) {
            connUseDetected.addEventListener('click', function () {
                var d = connectState.detected;
                if (!d) { showChooser(); return; }
                connUseDetected.disabled = true;
                connUseDetected.textContent = 'Connecting...';
                showStatus(connDetectedStatus, 'Connecting to ' + (d.label || d.provider) + '...', 'loading');

                var model = '';
                // For a key-already-configured provider, keep whatever model is
                // already saved; for Ollama, use the detected model name.
                if (d.provider === 'ollama') {
                    model = defaultModelFor('ollama');
                } else {
                    var bs = connectState.baseSettings || {};
                    model = bs[d.provider + '_model'] || DEFAULT_MODELS[d.provider] || '';
                }
                saveAndTest(d.provider, '', model, function (ok, msg, testedModel, soft) {
                    connUseDetected.disabled = false;
                    connUseDetected.textContent = 'Use it & continue';
                    if (ok) {
                        onConnected(d.provider, testedModel || model, soft);
                    } else {
                        showStatus(connDetectedStatus, msg || 'Could not connect. Try a different provider.', 'error');
                    }
                });
            });
        }

        if (connShowChooser) {
            connShowChooser.addEventListener('click', function () { showChooser(); });
        }

        // Provider card selection → reveal that provider's form.
        if (connCards) {
            connCards.querySelectorAll('.connect-card').forEach(function (card) {
                card.addEventListener('click', function () {
                    var prov = card.dataset.provider;
                    connectState.selected = prov;
                    connCards.querySelectorAll('.connect-card').forEach(function (c) { c.classList.remove('active'); });
                    card.classList.add('active');
                    // Toggle the matching form.
                    ['anthropic', 'openai', 'ollama', 'openrouter', 'google'].forEach(function (p) {
                        var f = document.getElementById('cf-' + p);
                        if (f) f.hidden = (p !== prov);
                    });
                    // Pre-fill model default (esp. detected Ollama model).
                    var modelInput = document.getElementById('cf-' + prov + '-model');
                    if (modelInput && prov === 'ollama' && !modelInput.value) {
                        modelInput.value = defaultModelFor('ollama');
                    }
                    hide(connStatus);
                    show(connFormWrap);
                    if (connFormWrap && typeof connFormWrap.scrollIntoView === 'function') {
                        connFormWrap.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
                    }
                });
            });
        }

        // Show/hide key toggles inside the connect forms.
        if (connFormWrap) {
            connFormWrap.querySelectorAll('.connect-show-key').forEach(function (btn) {
                btn.addEventListener('click', function () {
                    var input = btn.previousElementSibling;
                    if (input && input.tagName === 'INPUT') {
                        input.type = input.type === 'password' ? 'text' : 'password';
                        btn.textContent = input.type === 'password' ? 'Show' : 'Hide';
                    }
                });
            });
        }

        // POST /api/settings then GET /api/settings/test-connection.
        function saveAndTest(provider, apiKey, model, cb) {
            var bs = connectState.baseSettings || {};
            // Start from current settings so we don't clobber other providers'
            // models or the (validated) ollama base url, then override ours.
            var body = {
                provider: provider,
                api_key: apiKey || null,
                anthropic_model: bs.anthropic_model || DEFAULT_MODELS.anthropic,
                openai_model: bs.openai_model || DEFAULT_MODELS.openai,
                ollama_model: bs.ollama_model || 'llama3.2',
                ollama_base_url: bs.ollama_base_url || 'http://localhost:11434',
                openrouter_model: bs.openrouter_model || DEFAULT_MODELS.openrouter,
                google_model: bs.google_model || DEFAULT_MODELS.google,
                include_homework: (bs.include_homework !== undefined) ? bs.include_homework : true,
                export_format: bs.export_format || 'markdown'
            };
            if (model) body[provider + '_model'] = model;

            fetch('/api/settings', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(body)
            }).then(function (r) { return r.json().then(function (j) { return { ok: r.ok, data: j }; }); })
              .then(function (res) {
                if (!res.ok || (res.data && res.data.error)) {
                    cb(false, (res.data && res.data.error) || 'Could not save settings.', null);
                    return;
                }
                // Refresh cached settings to reflect the save.
                connectState.baseSettings = Object.assign({}, bs, { provider: provider });
                connectState.baseSettings[provider + '_model'] = model || body[provider + '_model'];
                return fetch('/api/settings/test-connection')
                    .then(function (r) { return r.json(); })
                    .then(function (t) {
                        if (t && t.connected) {
                            cb(true, t.message || '', t.model || model);
                            return;
                        }
                        // The connection tester only validates ollama / anthropic
                        // / openai. For other providers (openrouter, google) it
                        // returns "Unknown provider" — that's not a real failure,
                        // the settings saved fine. Confirm readiness via /health
                        // (key present) so we don't falsely block the teacher.
                        var errText = (t && (t.error || t.message)) || '';
                        if (/unknown provider/i.test(errText)) {
                            return fetch('/api/health')
                                .then(function (r) { return r.json(); })
                                .then(function (h) {
                                    if (h && h.llm_connected) {
                                        cb(true, '', (h.llm_model || model), true);
                                    } else {
                                        cb(false, 'Saved, but Claw-ED could not confirm a working key. Double-check your key and model, then try again.', null);
                                    }
                                });
                        }
                        cb(false, errText || 'The provider rejected the connection. Double-check your key and model.', null);
                    });
            }).catch(function (err) {
                cb(false, 'Connection error: ' + err, null);
            });
        }

        // "Connect" button in the chooser form.
        if (connSubmit) {
            connSubmit.addEventListener('click', function () {
                var prov = connectState.selected;
                if (!prov) { showStatus(connStatus, 'Pick a provider first.', 'error'); return; }

                var keyInput = document.getElementById('cf-' + prov + '-key');
                var modelInput = document.getElementById('cf-' + prov + '-model');
                var apiKey = keyInput ? keyInput.value.trim() : '';
                var model = modelInput ? modelInput.value.trim() : '';

                // Ollama needs no key; everyone else does (unless one is already saved).
                if (prov !== 'ollama' && !apiKey) {
                    var bs = connectState.baseSettings || {};
                    var alreadyHas = bs['has_' + prov + '_key'];
                    if (!alreadyHas) {
                        showStatus(connStatus, 'Please paste your API key above.', 'error');
                        if (keyInput) keyInput.focus();
                        return;
                    }
                }
                if (!model && prov === 'ollama') {
                    showStatus(connStatus, 'Enter the Ollama model name you pulled (e.g. qwen3.5).', 'error');
                    if (modelInput) modelInput.focus();
                    return;
                }

                connSubmit.disabled = true;
                connSubmit.textContent = 'Connecting...';
                showStatus(connStatus, 'Saving and testing your connection...', 'loading');

                saveAndTest(prov, apiKey, model, function (ok, msg, testedModel, soft) {
                    connSubmit.disabled = false;
                    connSubmit.textContent = 'Connect';
                    if (ok) {
                        onConnected(prov, testedModel || model, soft);
                    } else {
                        showStatus(connStatus, msg || 'Could not connect. Check your key and try again.', 'error');
                    }
                });
            });
        }

        // Reached a working connection — show the reassuring success state.
        // `soft` = saved + key present, but this provider isn't covered by the
        // live connection tester (openrouter/google); we phrase it honestly.
        function onConnected(provider, model, soft) {
            hide(connDetected);
            hide(connChooser);
            hide(connDetecting);
            var label = PROVIDER_LABELS[provider] || provider;
            if (connSuccessTitle) {
                if (model) {
                    connSuccessTitle.textContent = soft
                        ? (label + ' is set up — using ' + model + '!')
                        : ('Connected — using ' + model + '!');
                } else {
                    connSuccessTitle.textContent = soft
                        ? (label + ' is set up and ready!')
                        : ('Connected to ' + label + '!');
                }
            }
            show(connSuccess);
            // Refresh the top status bar dot so it flips to "Connected".
            refreshStatusBar();
        }

        function refreshStatusBar() {
            var dot = document.getElementById('status-dot');
            var txt = document.getElementById('status-text');
            if (!dot || !txt) return;
            fetch('/api/health').then(function (r) { return r.json(); }).then(function (data) {
                if (data.llm_connected) {
                    dot.className = 'status-dot connected';
                    txt.textContent = 'Connected';
                    txt.title = data.llm_model ? ('Model: ' + data.llm_model) : '';
                }
            }).catch(function () {});
        }

        // Continue from success → the setup path the teacher chose at Welcome.
        if (connContinue) {
            connContinue.addEventListener('click', function () {
                goToStep(wizardState.setupPath || 'step-2b');
            });
        }
        if (connReconnect) {
            connReconnect.addEventListener('click', function () { showChooser(); });
        }

        // Step 2A: File Upload
        var wizUploadZone = document.getElementById('wizard-upload-zone');
        var wizFileInput = document.getElementById('wizard-file-input');
        var wizFileList = document.getElementById('wizard-file-list');
        var wizAnalyzeBtn = document.getElementById('wizard-analyze-btn');
        var wizUploadForm = document.getElementById('wizard-upload-form');
        var wizUploadStatus = document.getElementById('wizard-upload-status');
        var wizUploadProgress = document.getElementById('wizard-upload-progress');
        var wizProgressBar = document.getElementById('wizard-progress-bar');
        var wizardFiles = [];

        if (wizUploadZone) {
            wizUploadZone.addEventListener('click', function () { wizFileInput.click(); });
            wizUploadZone.addEventListener('dragover', function (e) { e.preventDefault(); wizUploadZone.classList.add('dragover'); });
            wizUploadZone.addEventListener('dragleave', function () { wizUploadZone.classList.remove('dragover'); });
            wizUploadZone.addEventListener('drop', function (e) {
                e.preventDefault();
                wizUploadZone.classList.remove('dragover');
                addWizardFiles(e.dataTransfer.files);
            });
            wizFileInput.addEventListener('change', function () { addWizardFiles(wizFileInput.files); });
        }

        function addWizardFiles(files) {
            for (var i = 0; i < files.length; i++) wizardFiles.push(files[i]);
            renderWizardFiles();
        }

        function renderWizardFiles() {
            if (!wizFileList) return;
            wizFileList.innerHTML = '';
            wizardFiles.forEach(function (f, idx) {
                var div = document.createElement('div');
                div.className = 'file-item';
                div.innerHTML = '<span class="file-name">' + escHtml(f.name) + '</span>' +
                    '<button class="file-remove" data-idx="' + idx + '">&times;</button>';
                wizFileList.appendChild(div);
            });
            wizFileList.querySelectorAll('.file-remove').forEach(function (btn) {
                btn.addEventListener('click', function () {
                    wizardFiles.splice(parseInt(this.dataset.idx), 1);
                    renderWizardFiles();
                });
            });
            if (wizAnalyzeBtn) wizAnalyzeBtn.disabled = wizardFiles.length === 0;
        }

        if (wizUploadForm) {
            wizUploadForm.addEventListener('submit', function (e) {
                e.preventDefault();
                if (wizardFiles.length === 0) return;

                wizAnalyzeBtn.disabled = true;
                wizAnalyzeBtn.textContent = 'Analyzing...';
                wizUploadProgress.hidden = false;
                wizProgressBar.style.width = '30%';
                showStatus(wizUploadStatus, 'Uploading and analyzing your materials...', 'loading');

                var fd = new FormData();
                wizardFiles.forEach(function (f) { fd.append('files', f); });

                fetch('/api/ingest', { method: 'POST', body: fd }).then(function (r) {
                    wizProgressBar.style.width = '80%';
                    return r.json();
                }).then(function (data) {
                    wizProgressBar.style.width = '100%';
                    if (data.error) {
                        showStatus(wizUploadStatus, data.error, 'error');
                        wizAnalyzeBtn.disabled = false;
                        wizAnalyzeBtn.textContent = 'Analyze My Materials';
                    } else {
                        wizardState.teacherId = data.teacher_id;
                        wizardState.persona = data.persona;
                        updateOnboardingStep(data.teacher_id, 2);
                        showPersonaCard(data.persona);
                        goToStep('step-3');
                    }
                }).catch(function (err) {
                    showStatus(wizUploadStatus, 'Upload failed: ' + err, 'error');
                    wizAnalyzeBtn.disabled = false;
                    wizAnalyzeBtn.textContent = 'Analyze My Materials';
                });
            });
        }

        // Back buttons → return to the Connect step (which has its own
        // "different provider" controls and remembers the detect result).
        var back2a = document.getElementById('wizard-back-2a');
        var back2b = document.getElementById('wizard-back-2b');
        if (back2a) back2a.addEventListener('click', function () { goToStep('step-connect'); });
        if (back2b) back2b.addEventListener('click', function () { goToStep('step-connect'); });

        // Step 2B: Quick Persona Form
        var wizPersonaForm = document.getElementById('wizard-persona-form');
        var wizPersonaStatus = document.getElementById('wizard-persona-status');

        if (wizPersonaForm) {
            wizPersonaForm.addEventListener('submit', function (e) {
                e.preventDefault();
                var fd = new FormData(wizPersonaForm);
                var body = {
                    name: fd.get('name'),
                    subject_area: fd.get('subject_area'),
                    grade_levels: fd.get('grade_levels'),
                    teaching_style: fd.get('teaching_style'),
                    preferred_lesson_format: fd.get('preferred_lesson_format'),
                };

                showStatus(wizPersonaStatus, 'Creating your persona...', 'loading');

                fetch('/api/onboarding/persona-form', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(body),
                }).then(function (r) { return r.json(); }).then(function (data) {
                    if (data.error) {
                        showStatus(wizPersonaStatus, data.error, 'error');
                    } else {
                        wizardState.teacherId = data.teacher_id;
                        wizardState.persona = data.persona;
                        updateOnboardingStep(data.teacher_id, 2);
                        showPersonaCard(data.persona);
                        goToStep('step-3');
                    }
                }).catch(function (err) {
                    showStatus(wizPersonaStatus, 'Failed: ' + err, 'error');
                });
            });
        }

        // Step 3: Persona display
        function showPersonaCard(persona) {
            var nameEl = document.getElementById('persona-name-display');
            var tagsEl = document.getElementById('persona-tags');
            var detailsEl = document.getElementById('persona-details');
            var voiceEl = document.getElementById('persona-voice-sample');

            if (nameEl) nameEl.textContent = persona.name || 'Your Teaching Persona';
            if (tagsEl) {
                tagsEl.innerHTML = '';
                var style = (persona.teaching_style || '').replace(/_/g, ' ');
                if (style) tagsEl.innerHTML += '<span class="persona-badge">' + escHtml(style) + '</span>';
                var vocab = (persona.vocabulary_level || '').replace(/_/g, ' ');
                if (vocab) tagsEl.innerHTML += '<span class="persona-badge">' + escHtml(vocab) + '</span>';
                (persona.structural_preferences || []).forEach(function (p) {
                    tagsEl.innerHTML += '<span class="meta-tag">' + escHtml(p) + '</span>';
                });
            }
            if (detailsEl) {
                detailsEl.innerHTML =
                    '<p><strong>Subject:</strong> ' + escHtml(persona.subject_area || 'General') + '</p>' +
                    '<p><strong>Grades:</strong> ' + escHtml((persona.grade_levels || []).join(', ') || 'Not set') + '</p>' +
                    '<p><strong>Lesson Format:</strong> ' + escHtml(persona.preferred_lesson_format || 'I Do / We Do / You Do') + '</p>';
            }
            if (voiceEl && persona.voice_sample) {
                voiceEl.hidden = false;
                voiceEl.textContent = '"' + persona.voice_sample.substring(0, 200) + '..."';
            }
        }

        // Thumbs up/down
        var thumbsUp = document.getElementById('persona-thumbsup');
        var thumbsDown = document.getElementById('persona-thumbsdown');
        var editPanel = document.getElementById('persona-edit-panel');
        var toGenerate = document.getElementById('wizard-to-generate');

        if (thumbsUp) {
            thumbsUp.addEventListener('click', function () {
                if (toGenerate) toGenerate.hidden = false;
                updateOnboardingStep(wizardState.teacherId, 3);
            });
        }
        if (thumbsDown) {
            thumbsDown.addEventListener('click', function () {
                if (editPanel) editPanel.hidden = false;
                var p = wizardState.persona || {};
                var peName = document.getElementById('pe-name');
                var peSubject = document.getElementById('pe-subject');
                var peGrades = document.getElementById('pe-grades');
                var peStyle = document.getElementById('pe-style');
                if (peName) peName.value = p.name || '';
                if (peSubject) peSubject.value = p.subject_area || '';
                if (peGrades) peGrades.value = (p.grade_levels || []).join(', ');
                if (peStyle) peStyle.value = p.teaching_style || 'direct_instruction';
            });
        }

        // Persona edit form
        var personaEditForm = document.getElementById('persona-edit-form');
        if (personaEditForm) {
            personaEditForm.addEventListener('submit', function (e) {
                e.preventDefault();
                var fd = new FormData(personaEditForm);
                fetch('/api/onboarding/persona-form', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        name: fd.get('name'),
                        subject_area: fd.get('subject_area'),
                        grade_levels: fd.get('grade_levels'),
                        teaching_style: fd.get('teaching_style'),
                    }),
                }).then(function (r) { return r.json(); }).then(function (data) {
                    if (!data.error) {
                        wizardState.teacherId = data.teacher_id;
                        wizardState.persona = data.persona;
                        showPersonaCard(data.persona);
                        editPanel.hidden = true;
                        if (toGenerate) toGenerate.hidden = false;
                    }
                });
            });
        }

        // To generate button
        if (toGenerate) {
            toGenerate.addEventListener('click', function () {
                var p = wizardState.persona || {};
                var wgSubject = document.getElementById('wg-subject');
                var wgGrade = document.getElementById('wg-grade');
                if (wgSubject && p.subject_area) wgSubject.value = p.subject_area;
                if (wgGrade && p.grade_levels && p.grade_levels.length) wgGrade.value = p.grade_levels[0];
                goToStep('step-4');
            });
        }

        // Step 4: Generate first lesson
        var wizGenForm = document.getElementById('wizard-gen-form');
        var wizGenBtn = document.getElementById('wizard-gen-btn');
        var wizGenProgress = document.getElementById('wizard-gen-progress');
        var wizGenBar = document.getElementById('wizard-gen-bar');
        var wizGenLog = document.getElementById('wizard-gen-log');
        var wizGenProgressText = document.getElementById('wizard-gen-progress-text');

        if (wizGenForm) {
            wizGenForm.addEventListener('submit', function (e) {
                e.preventDefault();
                var fd = new FormData(wizGenForm);
                var topic = fd.get('topic');
                if (!topic) return;

                wizGenBtn.disabled = true;
                wizGenBtn.textContent = 'Generating...';
                wizGenProgress.hidden = false;
                wizGenLog.innerHTML = '';
                wizGenBar.style.width = '5%';

                var body = JSON.stringify({
                    topic: topic,
                    grade_level: fd.get('grade_level') || '8',
                    subject: fd.get('subject') || 'Science',
                    duration_weeks: parseInt(fd.get('duration_weeks')) || 1,
                    include_homework: true,
                    max_lessons: 3,
                });

                fetch('/api/full', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: body,
                }).then(function (response) {
                    var reader = response.body.getReader();
                    var decoder = new TextDecoder();
                    var buffer = '';
                    var progress = 10;

                    function read() {
                        reader.read().then(function (result) {
                            if (result.done) {
                                wizGenBar.style.width = '100%';
                                updateOnboardingStep(wizardState.teacherId, 5);
                                goToStep('step-5');
                                return;
                            }
                            buffer += decoder.decode(result.value, { stream: true });
                            var lines = buffer.split('\n');
                            buffer = lines.pop();

                            lines.forEach(function (line) {
                                if (line.startsWith('data:')) {
                                    try {
                                        var payload = JSON.parse(line.slice(5).trim());
                                        addWizardLogEntry(payload);
                                        progress = Math.min(progress + 10, 95);
                                        wizGenBar.style.width = progress + '%';

                                        if (payload.unit_id) {
                                            wizardState.unitId = payload.unit_id;
                                        }
                                        if (payload.lesson_id && !wizardState.lessonId) {
                                            wizardState.lessonId = payload.lesson_id;
                                        }
                                    } catch (ex) { /* skip */ }
                                }
                            });
                            read();
                        });
                    }
                    read();
                }).catch(function (err) {
                    showStatus(document.getElementById('wizard-gen-status'), 'Connection failed: ' + err, 'error');
                    wizGenBtn.disabled = false;
                    wizGenBtn.textContent = 'Generate!';
                });
            });
        }

        function addWizardLogEntry(payload) {
            if (!wizGenLog) return;
            var div = document.createElement('div');
            div.className = 'log-entry ' + (payload.status || '');
            var text = '';
            if (payload.step === 'unit') {
                text = payload.status === 'done'
                    ? 'Unit plan created: ' + (payload.title || '')
                    : 'Creating unit plan...';
            } else if (payload.step === 'lesson') {
                text = payload.status === 'done'
                    ? 'Lesson ' + payload.lesson_number + ': ' + (payload.title || '') + ' done'
                    : 'Generating lesson ' + (payload.lesson_number || '') + '...';
            } else if (payload.step === 'materials') {
                text = payload.status === 'done' ? 'Materials generated' : 'Generating materials...';
            } else if (payload.unit_id) {
                text = 'All done!';
                div.className = 'log-entry done';
            } else {
                text = payload.message || JSON.stringify(payload);
            }
            div.textContent = text;
            wizGenLog.appendChild(div);
            wizGenLog.scrollTop = wizGenLog.scrollHeight;
            if (wizGenProgressText) wizGenProgressText.textContent = text;
        }

        // Step 5: Success links
        var successExport = document.getElementById('success-export');
        var successShare = document.getElementById('success-share');
        if (successExport) {
            successExport.addEventListener('click', function (e) {
                e.preventDefault();
                if (wizardState.lessonId) {
                    window.open('/api/export/' + wizardState.lessonId + '?fmt=pdf', '_blank');
                }
            });
        }
        if (successShare) {
            successShare.addEventListener('click', function (e) {
                e.preventDefault();
                if (wizardState.lessonId) {
                    var url = window.location.origin + '/lesson/' + wizardState.lessonId;
                    if (navigator.clipboard) {
                        navigator.clipboard.writeText(url);
                        window.eduToast('Link copied: ' + url, 'success');
                    } else {
                        prompt('Copy this link:', url);
                    }
                }
            });
        }

        function updateOnboardingStep(teacherId, step) {
            if (!teacherId) return;
            fetch('/api/onboarding/step', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ teacher_id: teacherId, step: step }),
            }).catch(function () {});
        }
    }

    // ── Settings Page ────────────────────────────────────────────────
    var settingsForm = document.getElementById('settings-form');
    if (settingsForm) {
        // Provider radio toggle
        var radios = settingsForm.querySelectorAll('input[name="provider"]');
        radios.forEach(function (radio) {
            radio.addEventListener('change', function () {
                settingsForm.querySelectorAll('.radio-card').forEach(function (card) {
                    card.classList.remove('active');
                });
                radio.closest('.radio-card').classList.add('active');

                document.getElementById('anthropic-settings').hidden = radio.value !== 'anthropic';
                document.getElementById('openai-settings').hidden = radio.value !== 'openai';
                document.getElementById('ollama-settings').hidden = radio.value !== 'ollama';
            });
        });

        // Test connection
        var testBtn = document.getElementById('test-connection-btn');
        var connStatus = document.getElementById('connection-status');
        if (testBtn) {
            testBtn.addEventListener('click', function () {
                testBtn.disabled = true;
                testBtn.textContent = 'Testing...';
                showStatus(connStatus, 'Testing connection...', 'loading');

                fetch('/api/settings/test-connection').then(function (r) { return r.json(); }).then(function (data) {
                    testBtn.disabled = false;
                    testBtn.textContent = 'Test Connection';
                    if (data.connected) {
                        showStatus(connStatus, 'Connected \u2014 ' + data.model + ' is ready', 'success');
                    } else {
                        showStatus(connStatus, 'Connection failed: ' + (data.error || 'Unknown error'), 'error');
                    }
                }).catch(function (err) {
                    testBtn.disabled = false;
                    testBtn.textContent = 'Test Connection';
                    showStatus(connStatus, 'Test failed: ' + err, 'error');
                });
            });
        }

        // Save settings
        settingsForm.addEventListener('submit', function (e) {
            e.preventDefault();
            var provider = settingsForm.querySelector('input[name="provider"]:checked').value;
            var apiKey = '';
            if (provider === 'anthropic') apiKey = document.getElementById('anthropic-key').value;
            else if (provider === 'openai') apiKey = document.getElementById('openai-key').value;

            var body = {
                provider: provider,
                api_key: apiKey || null,
                anthropic_model: document.getElementById('anthropic-model').value,
                openai_model: document.getElementById('openai-model').value,
                ollama_model: document.getElementById('ollama-model').value,
                ollama_base_url: document.getElementById('ollama-url').value,
                include_homework: document.getElementById('include-homework').checked,
                export_format: document.getElementById('export-format').value,
            };

            var saveStatus = document.getElementById('settings-save-status');
            showStatus(saveStatus, 'Saving...', 'loading');

            fetch('/api/settings', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(body),
            }).then(function (r) { return r.json(); }).then(function (data) {
                if (data.status === 'saved') {
                    showStatus(saveStatus, 'Settings saved!', 'success');
                } else {
                    showStatus(saveStatus, 'Failed to save', 'error');
                }
            }).catch(function (err) {
                showStatus(saveStatus, 'Save failed: ' + err, 'error');
            });
        });

        // Danger zone
        var clearBtn = document.getElementById('clear-content-btn');
        if (clearBtn) {
            clearBtn.addEventListener('click', function () {
                if (!confirm('Are you sure? This will delete all generated units, lessons, materials, and feedback. Your persona will be kept.')) return;
                fetch('/api/settings/clear-content', { method: 'POST' }).then(function (r) { return r.json(); }).then(function (data) {
                    if (data.status === 'cleared') {
                        window.eduToast('All generated content has been cleared.', 'success');
                        window.location.reload();
                    }
                });
            });
        }

        var resetBtn = document.getElementById('reset-btn');
        if (resetBtn) {
            resetBtn.addEventListener('click', function () {
                if (!confirm('Are you sure? This will delete EVERYTHING \u2014 all content, your persona, and all settings. This cannot be undone.')) return;
                if (!confirm('Really? Type OK to confirm.')) return;
                fetch('/api/settings/reset', { method: 'POST' }).then(function (r) { return r.json(); }).then(function (data) {
                    if (data.status === 'reset') {
                        window.eduToast('Claw-ED has been reset.', 'success');
                        window.location.href = '/';
                    }
                });
            });
        }
    }

    // ── File Upload (Index Page — legacy, kept for non-wizard flow) ──
    var uploadZone = document.getElementById('upload-zone');
    var fileInput = document.getElementById('file-input');
    var fileList = document.getElementById('file-list');
    var ingestForm = document.getElementById('ingest-form');
    var ingestBtn = document.getElementById('ingest-btn');
    var ingestStatus = document.getElementById('ingest-status');
    var selectedFiles = [];

    if (uploadZone && fileInput) {
        uploadZone.addEventListener('click', function () { fileInput.click(); });
        uploadZone.addEventListener('dragover', function (e) {
            e.preventDefault();
            uploadZone.classList.add('dragover');
        });
        uploadZone.addEventListener('dragleave', function () {
            uploadZone.classList.remove('dragover');
        });
        uploadZone.addEventListener('drop', function (e) {
            e.preventDefault();
            uploadZone.classList.remove('dragover');
            addFiles(e.dataTransfer.files);
        });
        fileInput.addEventListener('change', function () {
            addFiles(fileInput.files);
        });
    }

    function addFiles(files) {
        for (var i = 0; i < files.length; i++) {
            selectedFiles.push(files[i]);
        }
        renderFileList();
    }

    function renderFileList() {
        if (!fileList) return;
        fileList.innerHTML = '';
        selectedFiles.forEach(function (f, idx) {
            var div = document.createElement('div');
            div.className = 'file-item';
            div.innerHTML = '<span class="file-name">' + escHtml(f.name) + '</span>' +
                '<button class="file-remove" data-idx="' + idx + '">&times;</button>';
            fileList.appendChild(div);
        });
        fileList.querySelectorAll('.file-remove').forEach(function (btn) {
            btn.addEventListener('click', function () {
                selectedFiles.splice(parseInt(this.dataset.idx), 1);
                renderFileList();
            });
        });
        if (ingestBtn) ingestBtn.disabled = selectedFiles.length === 0;
    }

    if (ingestForm) {
        ingestForm.addEventListener('submit', function (e) {
            e.preventDefault();
            if (selectedFiles.length === 0) return;

            var fd = new FormData();
            selectedFiles.forEach(function (f) { fd.append('files', f); });

            ingestBtn.disabled = true;
            ingestBtn.textContent = 'Analyzing...';
            showStatus(ingestStatus, 'Uploading and analyzing your materials...', 'loading');

            fetch('/api/ingest', { method: 'POST', body: fd })
                .then(function (r) { return r.json(); })
                .then(function (data) {
                    if (data.error) {
                        showStatus(ingestStatus, data.error, 'error');
                        ingestBtn.disabled = false;
                        ingestBtn.textContent = 'Extract Teaching Persona';
                    } else {
                        showStatus(ingestStatus,
                            'Persona extracted! Style: ' + (data.persona.teaching_style || '') +
                            ', Tone: ' + (data.persona.tone || '') +
                            '. Redirecting...', 'success');
                        setTimeout(function () { window.location.href = '/dashboard'; }, 1500);
                    }
                })
                .catch(function (err) {
                    showStatus(ingestStatus, 'Upload failed: ' + err, 'error');
                    ingestBtn.disabled = false;
                    ingestBtn.textContent = 'Extract Teaching Persona';
                });
        });
    }

    // ── Star Rating ──────────────────────────────────────────────────
    var starRating = document.getElementById('star-rating');
    var ratingValue = document.getElementById('rating-value');

    if (starRating) {
        var stars = starRating.querySelectorAll('.star');
        stars.forEach(function (star) {
            star.addEventListener('click', function () {
                var val = parseInt(this.dataset.value);
                ratingValue.value = val;
                stars.forEach(function (s) {
                    s.classList.toggle('active', parseInt(s.dataset.value) <= val);
                    s.textContent = parseInt(s.dataset.value) <= val ? '\u2605' : '\u2606';
                });
            });
            star.addEventListener('mouseenter', function () {
                var val = parseInt(this.dataset.value);
                stars.forEach(function (s) {
                    s.textContent = parseInt(s.dataset.value) <= val ? '\u2605' : '\u2606';
                });
            });
        });
        if (starRating) {
            starRating.addEventListener('mouseleave', function () {
                var val = parseInt(ratingValue.value);
                stars.forEach(function (s) {
                    s.textContent = parseInt(s.dataset.value) <= val ? '\u2605' : '\u2606';
                });
            });
        }
    }

    // ── Feedback Form ────────────────────────────────────────────────
    var feedbackForm = document.getElementById('feedback-form');
    var feedbackStatus = document.getElementById('feedback-status');

    if (feedbackForm) {
        feedbackForm.addEventListener('submit', function (e) {
            e.preventDefault();
            var fd = new FormData(feedbackForm);
            var rating = parseInt(fd.get('rating'));
            if (!rating || rating < 1) {
                showStatus(feedbackStatus, 'Please select a rating.', 'error');
                return;
            }
            var body = {
                lesson_id: fd.get('lesson_id'),
                rating: rating,
                notes: fd.get('notes') || ''
            };
            fetch('/api/feedback', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(body)
            })
            .then(function (r) { return r.json(); })
            .then(function (data) {
                if (data.error) {
                    showStatus(feedbackStatus, data.error, 'error');
                } else {
                    showStatus(feedbackStatus, 'Thank you for your feedback!', 'success');
                    window.eduToast('Feedback saved!', 'success');
                }
            })
            .catch(function (err) {
                showStatus(feedbackStatus, 'Failed: ' + err, 'error');
            });
        });
    }

    // ── Chat ─────────────────────────────────────────────────────────
    var chatForm = document.getElementById('chat-form');
    var chatMessages = document.getElementById('chat-messages');
    var chatInput = document.getElementById('chat-input');

    if (chatForm) {
        chatForm.addEventListener('submit', function (e) {
            e.preventDefault();
            var question = chatInput.value.trim();
            if (!question) return;

            var lessonId = chatForm.querySelector('[name=lesson_id]').value;
            appendChat('user', question);
            chatInput.value = '';

            fetch('/api/chat', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ lesson_id: lessonId, question: question })
            })
            .then(function (r) { return r.json(); })
            .then(function (data) {
                if (data.error) {
                    appendChat('assistant', 'Error: ' + data.error);
                } else {
                    appendChat('assistant', data.response);
                }
            })
            .catch(function (err) {
                appendChat('assistant', 'Connection error: ' + err);
            });
        });
    }

    function appendChat(role, text) {
        if (!chatMessages) return;
        var div = document.createElement('div');
        div.className = 'chat-msg ' + role;
        div.textContent = text;
        chatMessages.appendChild(div);
        chatMessages.scrollTop = chatMessages.scrollHeight;
    }

    // ── Helpers ───────────────────────────────────────────────────────
    function showStatus(el, msg, type) {
        if (!el) return;
        el.hidden = false;
        el.textContent = msg;
        el.className = 'status-box ' + type;
    }

    function escHtml(s) {
        var d = document.createElement('div');
        d.textContent = s;
        return d.innerHTML;
    }
});
