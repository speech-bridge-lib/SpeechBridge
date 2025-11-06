// Global variables
let currentJobId = null;
let statusCheckInterval = null;

// DOM elements
const uploadSection = document.getElementById('upload-section');
const progressSection = document.getElementById('progress-section');
const resultSection = document.getElementById('result-section');
const errorSection = document.getElementById('error-section');
const jobsSection = document.getElementById('jobs-section');

const uploadForm = document.getElementById('upload-form');
const videoFileInput = document.getElementById('video-file');
const fileName = document.getElementById('file-name');
const progressText = document.getElementById('progress-text');
const progressFill = document.getElementById('progress-fill');
const resultMessage = document.getElementById('result-message');
const errorMessage = document.getElementById('error-message');
const downloadBtn = document.getElementById('download-btn');
const newTranslationBtn = document.getElementById('new-translation-btn');
const retryBtn = document.getElementById('retry-btn');

const subtitleOnlyCheckbox = document.getElementById('subtitle-only');
const syncAudioCheckbox = document.getElementById('sync-audio');

// File input handling
videoFileInput.addEventListener('change', function() {
    if (this.files && this.files[0]) {
        fileName.textContent = this.files[0].name;
    } else {
        fileName.textContent = 'Choose a file or drag here';
    }
});

// Drag and drop handling
const fileLabel = document.querySelector('.file-label');

fileLabel.addEventListener('dragover', function(e) {
    e.preventDefault();
    this.style.borderColor = '#4a90e2';
    this.style.background = '#f0f7ff';
});

fileLabel.addEventListener('dragleave', function(e) {
    e.preventDefault();
    this.style.borderColor = '#e1e4e8';
    this.style.background = '#fafbfc';
});

fileLabel.addEventListener('drop', function(e) {
    e.preventDefault();
    this.style.borderColor = '#e1e4e8';
    this.style.background = '#fafbfc';

    const files = e.dataTransfer.files;
    if (files.length > 0) {
        videoFileInput.files = files;
        fileName.textContent = files[0].name;
    }
});

// Subtitle only checkbox handling
subtitleOnlyCheckbox.addEventListener('change', function() {
    if (this.checked) {
        syncAudioCheckbox.checked = false;
        syncAudioCheckbox.disabled = true;
    } else {
        syncAudioCheckbox.disabled = false;
    }
});

// Form submission
uploadForm.addEventListener('submit', async function(e) {
    e.preventDefault();

    const formData = new FormData();
    const videoFile = videoFileInput.files[0];

    if (!videoFile) {
        showError('Please select a video file');
        return;
    }

    // Add file and form fields
    formData.append('video', videoFile);
    formData.append('target_lang', document.getElementById('target-lang').value);
    formData.append('whisper_model', document.getElementById('whisper-model').value);
    formData.append('sync_audio', syncAudioCheckbox.checked ? 'true' : 'false');
    formData.append('generate_subtitles', document.getElementById('generate-subtitles').checked ? 'true' : 'false');
    formData.append('embed_subtitles', document.getElementById('embed-subtitles').checked ? 'true' : 'false');
    formData.append('subtitle_only', subtitleOnlyCheckbox.checked ? 'true' : 'false');

    // Show progress section
    showProgress();
    progressText.textContent = 'Uploading video...';
    progressFill.style.width = '10%';

    try {
        const response = await fetch('/upload', {
            method: 'POST',
            body: formData
        });

        const data = await response.json();

        if (!response.ok) {
            throw new Error(data.error || 'Upload failed');
        }

        currentJobId = data.job_id;
        progressText.textContent = 'Upload complete! Starting translation...';
        progressFill.style.width = '20%';

        // Start status polling
        startStatusPolling();

    } catch (error) {
        showError(error.message || 'Failed to upload video');
    }
});

// Status polling
function startStatusPolling() {
    if (statusCheckInterval) {
        clearInterval(statusCheckInterval);
    }

    statusCheckInterval = setInterval(checkStatus, 2000); // Check every 2 seconds
    checkStatus(); // Check immediately
}

async function checkStatus() {
    if (!currentJobId) return;

    try {
        const response = await fetch(`/status/${currentJobId}`);
        const data = await response.json();

        if (!response.ok) {
            throw new Error(data.error || 'Failed to check status');
        }

        // Update progress text
        progressText.textContent = data.progress;

        // Update progress bar based on status
        let progressPercent = 20;
        if (data.status === 'queued') {
            progressPercent = 20;
        } else if (data.status === 'processing') {
            progressPercent = 50;
        } else if (data.status === 'completed') {
            progressPercent = 100;
        }
        progressFill.style.width = progressPercent + '%';

        // Handle completed or failed status
        if (data.status === 'completed') {
            clearInterval(statusCheckInterval);
            showResult(data.result);
            loadJobs(); // Refresh jobs list
        } else if (data.status === 'failed') {
            clearInterval(statusCheckInterval);
            showError(data.error || 'Translation failed');
            loadJobs(); // Refresh jobs list
        }

    } catch (error) {
        clearInterval(statusCheckInterval);
        showError(error.message || 'Failed to check translation status');
    }
}

// Show/hide sections
function showProgress() {
    uploadSection.style.display = 'none';
    progressSection.style.display = 'block';
    resultSection.style.display = 'none';
    errorSection.style.display = 'none';
}

function showResult(result) {
    uploadSection.style.display = 'none';
    progressSection.style.display = 'none';
    resultSection.style.display = 'block';
    errorSection.style.display = 'none';

    resultMessage.textContent = result.message || 'Your video has been successfully translated!';
    downloadBtn.href = `/download/${currentJobId}`;
}

function showError(message) {
    uploadSection.style.display = 'none';
    progressSection.style.display = 'none';
    resultSection.style.display = 'none';
    errorSection.style.display = 'block';

    errorMessage.textContent = message;
}

function showUploadForm() {
    uploadSection.style.display = 'block';
    progressSection.style.display = 'none';
    resultSection.style.display = 'none';
    errorSection.style.display = 'none';

    // Reset form
    uploadForm.reset();
    fileName.textContent = 'Choose a file or drag here';
    currentJobId = null;

    if (statusCheckInterval) {
        clearInterval(statusCheckInterval);
    }
}

// Button handlers
newTranslationBtn.addEventListener('click', showUploadForm);
retryBtn.addEventListener('click', showUploadForm);

// Load jobs list
async function loadJobs() {
    try {
        const response = await fetch('/jobs');
        const data = await response.json();

        const jobsList = document.getElementById('jobs-list');

        if (data.jobs && data.jobs.length > 0) {
            jobsList.innerHTML = data.jobs.map(job => `
                <div class="job-item">
                    <div class="job-info">
                        <h4>${job.input_file}</h4>
                        <p>Language: ${job.config.target_lang} | Model: ${job.config.whisper_model}</p>
                    </div>
                    <span class="job-status ${job.status}">${job.status}</span>
                </div>
            `).join('');
        } else {
            jobsList.innerHTML = '<p class="no-jobs">No translations yet</p>';
        }
    } catch (error) {
        console.error('Failed to load jobs:', error);
    }
}

// Initialize
document.addEventListener('DOMContentLoaded', function() {
    loadJobs();

    // Load jobs every 10 seconds
    setInterval(loadJobs, 10000);
});
