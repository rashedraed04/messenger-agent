/**
 * Agent Chat Studio — Client Logic
 * Handles interactive chatting with the AI sales agent simulating a clean customer.
 */

document.addEventListener('DOMContentLoaded', () => {
    const chatMessages = document.getElementById('chat-messages');
    const chatForm = document.getElementById('chat-form');
    const chatInput = document.getElementById('chat-input');
    const btnSend = document.getElementById('btn-send-message');
    const typingIndicator = document.getElementById('typing-indicator');
    const btnReset = document.getElementById('btn-reset-chat');
    const btnReenableBot = document.getElementById('btn-reenable-bot');
    const handoffAlertBox = document.getElementById('handoff-alert-box');
    const handoffReasonText = document.getElementById('handoff-reason-text');
    const btnTogglePersona = document.getElementById('btn-toggle-persona');
    const personaPanel = document.getElementById('persona-panel');
    const customerNameOverride = document.getElementById('customer-name-override');
    const sessionDisplay = document.getElementById('session-psid-display');

    // Inspector elements
    const stateBadge = document.getElementById('inspector-state-badge');
    const slotName = document.getElementById('slot-name');
    const slotPhone = document.getElementById('slot-phone');
    const slotGov = document.getElementById('slot-governorate');
    const slotAddr = document.getElementById('slot-address');
    const slotFee = document.getElementById('slot-fee');
    const slotProductsList = document.getElementById('slot-products-list');
    const diagModel = document.getElementById('diag-model');
    const diagLatency = document.getElementById('diag-latency');
    const diagIntent = document.getElementById('diag-intent');

    // Photo attachment (simulates a customer sending a product photo)
    const imageInput = document.getElementById('chat-image-input');
    const btnAttachImage = document.getElementById('btn-attach-image');
    const btnRemoveImage = document.getElementById('btn-remove-image');
    const imagePreview = document.getElementById('image-preview');
    const imagePreviewThumb = document.getElementById('image-preview-thumb');
    const MAX_IMAGE_BYTES = 5 * 1024 * 1024;

    let currentSessionId = getCookie('admin_sim_psid') || '';
    let pendingImageDataUrl = null;

    function clearPendingImage() {
        pendingImageDataUrl = null;
        if (imageInput) imageInput.value = '';
        if (imagePreview) imagePreview.style.display = 'none';
    }

    if (btnAttachImage && imageInput) {
        btnAttachImage.addEventListener('click', () => imageInput.click());
        imageInput.addEventListener('change', () => {
            const file = imageInput.files && imageInput.files[0];
            if (!file) return;
            if (file.size > MAX_IMAGE_BYTES) {
                if (typeof showToast === 'function') showToast('حجم الصورة أكبر من 5 ميغابايت', 'danger');
                clearPendingImage();
                return;
            }
            const reader = new FileReader();
            reader.onload = () => {
                pendingImageDataUrl = reader.result;
                imagePreviewThumb.src = pendingImageDataUrl;
                imagePreview.style.display = 'flex';
                if (chatInput) chatInput.focus();
            };
            reader.readAsDataURL(file);
        });
    }
    if (btnRemoveImage) btnRemoveImage.addEventListener('click', clearPendingImage);

    // Scroll chat to bottom
    function scrollToBottom() {
        if (chatMessages) {
            chatMessages.scrollTop = chatMessages.scrollHeight;
        }
    }
    scrollToBottom();

    // Helper: read cookie
    function getCookie(name) {
        const matches = document.cookie.match(new RegExp(
            "(?:^|; )" + name.replace(/([\.$?*|{}\(\)\[\]\\\/\+^])/g, '\\$1') + "=([^;]*)"
        ));
        return matches ? decodeURIComponent(matches[1]) : undefined;
    }

    // Toggle persona panel
    if (btnTogglePersona && personaPanel) {
        btnTogglePersona.addEventListener('click', () => {
            const isHidden = personaPanel.style.display === 'none';
            personaPanel.style.display = isHidden ? 'block' : 'none';
            if (isHidden && customerNameOverride) {
                customerNameOverride.focus();
            }
        });
    }

    // Helper: format current time HH:MM
    function getCurrentTimeStr() {
        const now = new Date();
        const h = String(now.getHours()).padStart(2, '0');
        const m = String(now.getMinutes()).padStart(2, '0');
        return `${h}:${m}`;
    }

    // Append user message bubble
    function appendCustomerBubble(text, imageDataUrl) {
        const row = document.createElement('div');
        row.className = 'msg-row inbound';

        const bubble = document.createElement('div');
        bubble.className = 'msg-bubble inbound';

        const nameLabel = customerNameOverride && customerNameOverride.value.trim() 
            ? `👤 ${customerNameOverride.value.trim()} (أنت)` 
            : '👤 أنت (عميل بدون تفضيلات)';

        bubble.innerHTML = `
            <div class="msg-header">
                <span class="fw-bold">${escapeHtml(nameLabel)}</span>
                <span>${getCurrentTimeStr()}</span>
            </div>
            <div class="msg-body" style="white-space: pre-line;">${escapeHtml(text)}</div>
        `;
        if (imageDataUrl) {
            const img = document.createElement('img');
            img.src = imageDataUrl;
            img.alt = 'صورة أرسلها العميل';
            img.style.cssText = 'max-width: 220px; max-height: 220px; border-radius: 8px; display: block; margin-top: 6px;';
            bubble.querySelector('.msg-body').before(img);
        }
        row.appendChild(bubble);

        // Insert before typing indicator
        if (typingIndicator && typingIndicator.parentElement) {
            chatMessages.insertBefore(row, typingIndicator.parentElement);
        } else {
            chatMessages.appendChild(row);
        }
        scrollToBottom();
    }

    // Append agent response bubble
    function appendAgentBubble(text, aiMeta) {
        const row = document.createElement('div');
        row.className = 'msg-row outbound';

        const bubble = document.createElement('div');
        bubble.className = 'msg-bubble outbound';

        let footerHtml = '';
        if (aiMeta) {
            const parts = [];
            if (aiMeta.model_name) parts.push(`<span>موديل: ${escapeHtml(aiMeta.model_name)}</span>`);
            if (aiMeta.intent) parts.push(`<span>قصد: ${escapeHtml(aiMeta.intent)}</span>`);
            if (aiMeta.latency_ms) parts.push(`<span>استجابة: ${Math.round(aiMeta.latency_ms)}ms</span>`);
            if (parts.length > 0) {
                footerHtml = `<div class="msg-footer">${parts.join('')}</div>`;
            }
        }

        bubble.innerHTML = `
            <div class="msg-header">
                <span class="fw-bold">🤖 الوكيل الذكي</span>
                <span>${getCurrentTimeStr()}</span>
            </div>
            <div class="msg-body" style="white-space: pre-line;">${escapeHtml(text)}</div>
            ${footerHtml}
        `;
        row.appendChild(bubble);

        if (typingIndicator && typingIndicator.parentElement) {
            chatMessages.insertBefore(row, typingIndicator.parentElement);
        } else {
            chatMessages.appendChild(row);
        }
        scrollToBottom();
    }

    // Escape HTML
    function escapeHtml(str) {
        if (!str) return '';
        const div = document.createElement('div');
        div.textContent = str;
        return div.innerHTML;
    }

    // Update state badge
    function updateStateBadge(state) {
        if (!stateBadge) return;
        stateBadge.textContent = state || 'DISCOVERY';

        // Clear existing bg classes
        stateBadge.className = 'badge state-badge';
        switch (state) {
            case 'DISCOVERY':
                stateBadge.classList.add('bg-primary');
                break;
            case 'PRODUCT_SELECTION':
                stateBadge.classList.add('bg-info', 'text-dark');
                break;
            case 'COLLECTING_DETAILS':
                stateBadge.classList.add('bg-warning', 'text-dark');
                break;
            case 'AWAITING_CONFIRMATION':
                stateBadge.classList.add('bg-purple', 'bg-gradient');
                stateBadge.style.backgroundColor = '#aa7c11';
                break;
            case 'CONFIRMED':
                stateBadge.classList.add('bg-success');
                break;
            case 'CANCELLED':
                stateBadge.classList.add('bg-danger');
                break;
            case 'HUMAN_HANDOFF':
                stateBadge.classList.add('bg-danger');
                break;
            default:
                stateBadge.classList.add('bg-secondary');
        }
    }

    // Update slots in Inspector
    function updateSlots(slots) {
        if (!slots) slots = {};
        if (slotName) slotName.textContent = slots.customer_name || '—';
        if (slotPhone) slotPhone.textContent = slots.customer_phone || '—';
        if (slotGov) slotGov.textContent = slots.governorate || '—';
        if (slotAddr) slotAddr.textContent = slots.address_detail || '—';
        if (slotFee) {
            slotFee.textContent = slots.delivery_fee_jod 
                ? `${parseFloat(slots.delivery_fee_jod).toFixed(3)} د.أ` 
                : '—';
        }

        if (slotProductsList) {
            if (slots.products && slots.products.length > 0) {
                slotProductsList.innerHTML = slots.products.map(p => `
                    <div class="d-flex justify-content-between align-items-center small p-1 rounded bg-dark mb-1">
                        <span>🧴 ${escapeHtml(p.product_name || p.name_match)}</span>
                        <span class="badge bg-primary">× ${p.quantity || 1}</span>
                    </div>
                `).join('');
            } else {
                slotProductsList.innerHTML = '<span class="text-secondary small">لم يختر أي منتج بعد</span>';
            }
        }
    }

    // Update diagnostics
    function updateDiagnostics(meta) {
        if (!meta) return;
        if (diagModel && meta.model_name) diagModel.textContent = meta.model_name;
        if (diagLatency && meta.latency_ms) diagLatency.textContent = `${Math.round(meta.latency_ms)} ms`;
        if (diagIntent && meta.intent) diagIntent.textContent = meta.intent;
    }

    // Update handoff box
    function updateHandoffAlert(isHandoff, reason) {
        if (!handoffAlertBox) return;
        if (isHandoff) {
            handoffAlertBox.style.display = 'block';
            if (handoffReasonText) handoffReasonText.textContent = reason || 'طلب تحويل يدوي';
        } else {
            handoffAlertBox.style.display = 'none';
        }
    }

    // Send customer message handler
    async function sendMessage(text) {
        const cleanText = (text || '').trim();
        const imageDataUrl = pendingImageDataUrl;
        if (!cleanText && !imageDataUrl) return;

        // 1. Render user bubble
        appendCustomerBubble(cleanText, imageDataUrl);
        if (chatInput) chatInput.value = '';
        clearPendingImage();

        // 2. Lock UI & show typing indicator
        if (btnSend) btnSend.disabled = true;
        if (chatInput) chatInput.disabled = true;
        if (typingIndicator) typingIndicator.style.display = 'flex';
        scrollToBottom();

        const custName = customerNameOverride ? customerNameOverride.value.trim() : null;

        try {
            const resp = await fetch('/dashboard/chat/send', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRF-Token': getCsrfToken(),
                },
                body: JSON.stringify({
                    message: cleanText,
                    image_data_url: imageDataUrl,
                    customer_name: custName,
                    session_id: currentSessionId,
                }),
            });

            const data = await resp.json();

            // Hide typing
            if (typingIndicator) typingIndicator.style.display = 'none';

            if (!resp.ok || !data.success) {
                const errMsg = data.error || 'حدث خطأ في استجابة الخادم';
                appendAgentBubble(`⚠️ ${errMsg}`);
                if (typeof showToast === 'function') showToast(errMsg, 'danger');
                return;
            }

            // Update current session if changed
            if (data.session_id) {
                currentSessionId = data.session_id;
                if (sessionDisplay) sessionDisplay.textContent = `الجلسة: ${data.session_id}`;
            }

            // Render agent responses
            if (data.replies && data.replies.length > 0) {
                data.replies.forEach((reply, idx) => {
                    // Only attach AI metadata to the last reply in batch
                    const meta = (idx === data.replies.length - 1) ? data.ai_metadata : null;
                    appendAgentBubble(reply, meta);
                });
            } else if (data.conversation && data.conversation.is_human_handoff) {
                appendAgentBubble('⚠️ تم تحويل المحادثة لموظف بشري؛ البوت الآلي في وضع السكون لهذه الجلسة.');
            }

            // Update inspector
            if (data.conversation) {
                updateStateBadge(data.conversation.state);
                updateSlots(data.conversation.collected_slots);
                updateHandoffAlert(data.conversation.is_human_handoff, data.conversation.handoff_reason);
            }
            if (data.ai_metadata) {
                updateDiagnostics(data.ai_metadata);
            }

        } catch (err) {
            console.error('Chat error:', err);
            if (typingIndicator) typingIndicator.style.display = 'none';
            appendAgentBubble('عذراً، تعذر الاتصال بالخادم. يرجى المحاولة مرة أخرى.');
            if (typeof showToast === 'function') showToast('تعذر الاتصال بالخادم', 'danger');
        } finally {
            if (btnSend) btnSend.disabled = false;
            if (chatInput) {
                chatInput.disabled = false;
                chatInput.focus();
            }
            scrollToBottom();
        }
    }

    // Form submit listener
    if (chatForm) {
        chatForm.addEventListener('submit', (e) => {
            e.preventDefault();
            if (chatInput) {
                sendMessage(chatInput.value);
            }
        });
    }

    // Quick prompts click
    const quickPromptsContainer = document.getElementById('quick-prompts');
    if (quickPromptsContainer) {
        quickPromptsContainer.addEventListener('click', (e) => {
            const chip = e.target.closest('.prompt-chip');
            if (chip && chip.dataset.prompt) {
                sendMessage(chip.dataset.prompt);
            }
        });
    }

    // Reset button
    if (btnReset) {
        btnReset.addEventListener('click', async () => {
            if (!confirm('هل تريد تصفير المحادثة وبدء جلسة جديدة كأي عميل بدون أي تفضيلات؟')) {
                return;
            }

            try {
                btnReset.disabled = true;
                const resp = await fetch('/dashboard/chat/reset', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': getCsrfToken() },
                    body: JSON.stringify({ session_id: currentSessionId, clear_history: true }),
                });

                const data = await resp.json();
                if (data.success) {
                    currentSessionId = data.session_id;
                    if (sessionDisplay) sessionDisplay.textContent = `الجلسة: ${data.session_id}`;

                    // Clear messages
                    if (chatMessages) {
                        chatMessages.innerHTML = `
                            <div class="msg-row outbound">
                                <div class="msg-bubble outbound">
                                    <div class="msg-header">
                                        <span class="fw-bold">🤖 الوكيل الذكي</span>
                                        <span>الآن</span>
                                    </div>
                                    <div class="msg-body" style="white-space: pre-line;">يا هلا فيك بمتجر التقوى! 🌹 تفضل كيف بقدر أساعدك اليوم؟ حابب تستفسر عن منتج معين أو تشوف الكتالوج؟</div>
                                    <div class="msg-footer">
                                        <span>💡 تم تصفير الجلسة بنجاح — أنت تتحدث الآن كعميل عام جديد بدون أي تفضيلات مسبقة.</span>
                                    </div>
                                </div>
                            </div>
                            <div class="msg-row outbound">
                                <div class="typing-indicator" id="typing-indicator">
                                    <div class="typing-dot"></div>
                                    <div class="typing-dot"></div>
                                    <div class="typing-dot"></div>
                                </div>
                            </div>
                        `;
                    }

                    // Reset inspector
                    updateStateBadge('DISCOVERY');
                    updateSlots({});
                    updateHandoffAlert(false);
                    if (diagLatency) diagLatency.textContent = '—';
                    if (diagIntent) diagIntent.textContent = '—';
                    if (customerNameOverride) customerNameOverride.value = '';

                    if (typeof showToast === 'function') {
                        showToast('تم بدء جلسة جديدة كعميل بدون أي تفضيلات مسبقة 🌹', 'success');
                    }
                }
            } catch (err) {
                console.error('Reset error:', err);
                if (typeof showToast === 'function') showToast('تعذر تصفير الجلسة', 'danger');
            } finally {
                btnReset.disabled = false;
            }
        });
    }

    // Re-enable bot from handoff
    if (btnReenableBot) {
        btnReenableBot.addEventListener('click', async () => {
            try {
                btnReenableBot.disabled = true;
                const resp = await fetch('/dashboard/chat/handoff-toggle', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': getCsrfToken() },
                    body: JSON.stringify({ session_id: currentSessionId, is_handoff: false }),
                });
                const data = await resp.json();
                if (data.success) {
                    updateHandoffAlert(false);
                    updateStateBadge(data.state);
                    appendAgentBubble('🤖 تم إعادة تفعيل البوت الآلي لهذه الجلسة بنجاح.');
                    if (typeof showToast === 'function') showToast('تم إعادة تفعيل البوت بنجاح', 'success');
                }
            } catch (err) {
                console.error('Reenable bot error:', err);
            } finally {
                btnReenableBot.disabled = false;
            }
        });
    }
});
