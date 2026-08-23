/* =========================================================
   HerPulse — API helper
   Every page includes this file. It centralizes all calls to
   the Flask backend. We deliberately avoid localStorage /
   sessionStorage: auth + questionnaire progress are tracked
   server-side via the Flask session cookie, so every fetch
   below sends credentials: 'include'.
   ========================================================= */

const API_BASE = window.location.origin.includes('file://')
  ? 'http://127.0.0.1:5000'   // opened directly as a file, point at local Flask dev server
  : '';                        // served BY Flask, use relative paths

async function apiRequest(path, options = {}) {
  const res = await fetch(API_BASE + path, {
    credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    ...options,
  });

  let data = null;
  try { data = await res.json(); } catch (e) { /* no body */ }

  if (!res.ok) {
    const message = (data && data.error) || `Request failed (${res.status})`;
    throw new Error(message);
  }
  return data;
}

const HerPulseAPI = {
  login: (username, password) =>
    apiRequest('/api/login', { method: 'POST', body: JSON.stringify({ username, password }) }),

  logout: () => apiRequest('/api/logout', { method: 'POST' }),

  me: () => apiRequest('/api/me'),

  deviceStatus: () => apiRequest('/api/device/status'),

  connectDevice: (deviceId, devicePassword) =>
    apiRequest('/api/device/connect', { method: 'POST', body: JSON.stringify({ device_id: deviceId, device_password: devicePassword }) }),

  getQuestions: () => apiRequest('/api/questions'),

  submitAnswers: (answers) =>
    apiRequest('/api/submit-answers', { method: 'POST', body: JSON.stringify({ answers }) }),

  startProcessing: () => apiRequest('/api/process/start', { method: 'POST' }),

  getProcessingStatus: () => apiRequest('/api/process/status'),

  getReport: () => apiRequest('/api/report'),
};

/* Redirect helper: guard pages that require an active login/session. */
async function requireSession(redirectTo = 'login.html') {
  try {
    await HerPulseAPI.me();
  } catch (e) {
    window.location.href = redirectTo;
  }
}
