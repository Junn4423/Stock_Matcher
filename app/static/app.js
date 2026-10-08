const form = document.getElementById('job-form');
const fileInput = document.getElementById('file');
const fileName = document.getElementById('file-name');
const dropzone = document.getElementById('dropzone');
const submitButton = document.getElementById('submit-button');
const statusPanel = document.getElementById('status-panel');
const statusTitle = document.getElementById('status-title');
const statusBadge = document.getElementById('status-badge');
const progressBar = document.getElementById('progress-bar');
const progressText = document.getElementById('progress-text');
const rateLimit = document.getElementById('rate-limit');
const warnings = document.getElementById('warnings');
const downloadLink = document.getElementById('download-link');
const quotaBadge = document.getElementById('quota-badge');
const apiKeyInput = document.getElementById('api_key');
const ttsVoiceSelect = document.getElementById('tts_voice');
const voiceDesc = document.getElementById('voice-desc');
const logConsole = document.getElementById('log-console');

let voiceCatalogMap = {};

fileInput.addEventListener('change', () => {
  fileName.textContent = fileInput.files?.[0]?.name || 'Chưa chọn file';
});

['dragenter','dragover'].forEach(name => dropzone.addEventListener(name, event => {event.preventDefault(); dropzone.classList.add('drag');}));
['dragleave','drop'].forEach(name => dropzone.addEventListener(name, event => {event.preventDefault(); dropzone.classList.remove('drag');}));
dropzone.addEventListener('drop', event => {
  const files = event.dataTransfer?.files;
  if (files?.length) { fileInput.files = files; fileName.textContent = files[0].name; }
});

async function fetchQuota() {
  const apiKey = apiKeyInput.value.trim();
  try {
    const res = await fetch(`/api/pexels/quota?api_key=${encodeURIComponent(apiKey)}`);
    const data = await res.json();
    if (data.configured && data.remaining !== undefined) {
      quotaBadge.textContent = `Pexels Quota: ${data.remaining}/${data.limit} remaining/hour`;
      quotaBadge.className = 'quota-badge active';
      rateLimit.textContent = `Pexels quota còn ${data.remaining}/${data.limit}`;
    } else if (data.message) {
      quotaBadge.textContent = `Pexels Quota: ${data.message}`;
      quotaBadge.className = 'quota-badge warning';
    } else if (data.error) {
      quotaBadge.textContent = `Pexels Quota: ${data.error}`;
      quotaBadge.className = 'quota-badge error';
    }
  } catch (err) {
    quotaBadge.textContent = 'Pexels Quota: Không kết nối được API';
  }
}

async function loadVoiceCatalog() {
  try {
    const res = await fetch('/api/tts/voices');
    const data = await res.json();
    if (data.voices?.length) {
      ttsVoiceSelect.innerHTML = '';
      data.voices.forEach(v => {
        voiceCatalogMap[v.id] = v;
        const opt = document.createElement('option');
        opt.value = v.id;
        opt.textContent = `${v.name} • [${v.engine}]`;
        ttsVoiceSelect.appendChild(opt);
      });
      updateVoiceDesc();
    }
  } catch (e) {
    LOGGER?.error?.(e);
  }
}

function updateVoiceDesc() {
  const selectedId = ttsVoiceSelect.value;
  const item = voiceCatalogMap[selectedId];
  if (item) {
    voiceDesc.innerHTML = `<strong>Engine:</strong> ${item.engine} | <strong>Model:</strong> ${item.model}<br>${item.description}`;
  }
}

ttsVoiceSelect.addEventListener('change', updateVoiceDesc);
apiKeyInput.addEventListener('blur', fetchQuota);

function showError(message) {
  statusPanel.classList.remove('hidden');
  statusTitle.textContent = message;
  statusBadge.textContent = 'FAILED';
  progressBar.style.width = '100%';
  progressText.textContent = 'Lỗi';
  submitButton.disabled = false;
}

function renderLogs(logs) {
  if (!logs || !logs.length) {
    logConsole.classList.add('hidden');
    return;
  }
  logConsole.classList.remove('hidden');
  logConsole.innerHTML = logs.map(line => `<div>${line.replaceAll('<','&lt;')}</div>`).join('');
  logConsole.scrollTop = logConsole.scrollHeight;
}

async function pollJob(jobId) {
  while (true) {
    const response = await fetch(`/api/jobs/${jobId}`, {cache:'no-store'});
    const job = await response.json();
    if (!response.ok) throw new Error(job.detail || 'Không đọc được trạng thái job.');

    statusTitle.textContent = job.message || 'Đang xử lý';
    statusBadge.textContent = String(job.status || '').toUpperCase();
    const progress = Number(job.progress || 0);
    progressBar.style.width = `${progress}%`;
    progressText.textContent = `${progress}%`;

    const remaining = job.rate_limit?.['X-Ratelimit-Remaining'];
    const limit = job.rate_limit?.['X-Ratelimit-Limit'];
    if (remaining !== undefined) {
      rateLimit.textContent = `Pexels quota còn ${remaining}/${limit || '?'}`;
      quotaBadge.textContent = `Pexels Quota: ${remaining}/${limit || '?'} remaining/hour`;
    }

    renderLogs(job.log_history);

    if (job.warnings?.length) {
      warnings.classList.remove('hidden');
      warnings.innerHTML = `<strong>Cảnh báo:</strong><br>${job.warnings.map(item => String(item).replaceAll('<','&lt;')).join('<br>')}`;
    }

    if (job.status === 'completed') {
      downloadLink.href = job.download_url;
      downloadLink.classList.remove('hidden');
      downloadLink.textContent = `Tải ZIP • ${job.matched_count || 0}/${job.segment_count || 0} đoạn có video`;
      submitButton.disabled = false;
      fetchQuota();
      return;
    }
    if (job.status === 'failed') {
      submitButton.disabled = false;
      fetchQuota();
      throw new Error(job.message || 'Job thất bại.');
    }
    await new Promise(resolve => setTimeout(resolve, 800));
  }
}

form.addEventListener('submit', async event => {
  event.preventDefault();
  submitButton.disabled = true;
  statusPanel.classList.remove('hidden');
  downloadLink.classList.add('hidden');
  warnings.classList.add('hidden');
  logConsole.innerHTML = '';
  logConsole.classList.add('hidden');
  statusTitle.textContent = 'Đang gửi transcript…';
  statusBadge.textContent = 'STARTING';
  progressBar.style.width = '2%';
  progressText.textContent = '2%';

  try {
    const body = new FormData(form);
    const response = await fetch('/api/jobs', {method:'POST', body});
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || 'Không tạo được job.');
    await pollJob(data.job_id);
  } catch (error) {
    showError(error.message || String(error));
  }
});

// Initial load
fetchQuota();
loadVoiceCatalog();
