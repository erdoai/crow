/* crow dashboard JS */

function showError(msg) {
    const el = document.getElementById('auth-error');
    if (el) { el.textContent = msg; el.classList.remove('hidden'); }
}

function hideError() {
    const el = document.getElementById('auth-error');
    if (el) el.classList.add('hidden');
}

function showStatus(msg) {
    const el = document.getElementById('auth-status');
    if (el) { el.textContent = msg; el.classList.remove('hidden'); }
}

/* OTP auto-advance */
document.querySelectorAll('.otp-digit').forEach(input => {
    input.addEventListener('input', e => {
        const val = e.target.value;
        if (val && val.length === 1) {
            const idx = parseInt(e.target.dataset.idx);
            const next = document.querySelector(`.otp-digit[data-idx="${idx + 1}"]`);
            if (next) next.focus();
        }
    });
    input.addEventListener('keydown', e => {
        if (e.key === 'Backspace' && !e.target.value) {
            const idx = parseInt(e.target.dataset.idx);
            const prev = document.querySelector(`.otp-digit[data-idx="${idx - 1}"]`);
            if (prev) { prev.focus(); prev.value = ''; }
        }
    });
    input.addEventListener('paste', e => {
        e.preventDefault();
        const text = (e.clipboardData || window.clipboardData).getData('text').trim();
        const digits = text.replace(/\D/g, '').slice(0, 6);
        document.querySelectorAll('.otp-digit').forEach((el, i) => {
            el.value = digits[i] || '';
        });
        if (digits.length === 6) {
            document.querySelector(`.otp-digit[data-idx="5"]`).focus();
        }
    });
});

function getOtpCode() {
    return Array.from(document.querySelectorAll('.otp-digit')).map(el => el.value).join('');
}

/* Auth flows */
async function sendCode() {
    hideError();
    const email = document.getElementById('email-input').value.trim();
    if (!email) return showError('please enter your email');

    showStatus('sending code...');
    try {
        const res = await fetch('/auth/send-code', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ email }),
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || 'failed to send code');

        document.getElementById('email-step').classList.add('hidden');
        document.getElementById('code-step').classList.remove('hidden');
        document.getElementById('code-email').textContent = email;
        document.getElementById('auth-status').classList.add('hidden');
        document.querySelector('.otp-digit[data-idx="0"]').focus();
    } catch (err) {
        document.getElementById('auth-status').classList.add('hidden');
        showError(err.message);
    }
}

async function verifyCode() {
    hideError();
    const email = document.getElementById('email-input').value.trim();
    const code = getOtpCode();
    if (code.length !== 6) return showError('please enter the full 6-digit code');

    try {
        const res = await fetch('/auth/verify', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ email, code }),
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || 'verification failed');
        window.location.href = data.redirect;
    } catch (err) {
        showError(err.message);
    }
}

function backToEmail() {
    document.getElementById('code-step').classList.add('hidden');
    document.getElementById('email-step').classList.remove('hidden');
    document.querySelectorAll('.otp-digit').forEach(el => el.value = '');
    hideError();
}

/* Onboarding */
async function submitOnboarding() {
    hideError();
    const name = document.getElementById('name-input').value.trim();
    if (!name) return showError('please enter your name');

    try {
        const res = await fetch('/onboarding', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ display_name: name }),
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || 'failed');
        window.location.href = data.redirect;
    } catch (err) {
        showError(err.message);
    }
}

/* Dashboard actions */
async function createApiKey() {
    const input = document.getElementById('key-name-input');
    const name = input.value.trim();
    if (!name) return;

    try {
        const res = await fetch('/dashboard/api-keys', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name }),
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || 'failed');

        const result = document.getElementById('new-key-result');
        result.textContent = `copy this key now (it won't be shown again): ${data.key}`;
        result.classList.remove('hidden');
        input.value = '';

        // Reload after a delay to show the key in the list
        setTimeout(() => window.location.reload(), 5000);
    } catch (err) {
        alert(err.message);
    }
}

async function deleteApiKey(keyId) {
    if (!confirm('revoke this API key?')) return;
    try {
        const res = await fetch(`/dashboard/api-keys/${keyId}`, { method: 'DELETE' });
        if (!res.ok) throw new Error('failed');
        window.location.reload();
    } catch (err) {
        alert(err.message);
    }
}
