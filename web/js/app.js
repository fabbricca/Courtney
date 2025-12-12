/**
 * GLaDOS Web Interface - Main Application
 */

import GLaDOSWebSocket from './websocket.js';
import { AudioCapture, AudioPlayer, float32ToBase64PCM } from './audio.js';
import { LoginManager } from './login.js';

// Application state
const state = {
    ws: null,
    audioCapture: null,
    audioPlayer: null,
    loginManager: null,
    currentUser: null,
    messages: [],
    historyOffset: 0,
    historyLimit: 50,
    hasMoreHistory: true,
    audioEnabled: true,
    wakeLock: null,
    showTimestamps: true
};

// DOM elements
const elements = {
    // Login screen
    loginScreen: document.getElementById('login-screen'),
    usernameInput: document.getElementById('username-input'),
    passwordInput: document.getElementById('password-input'),
    rememberMeCheckbox: document.getElementById('remember-me'),
    loginBtn: document.getElementById('login-btn'),
    loginError: document.getElementById('login-error'),
    serverUrl: document.getElementById('server-url'),

    // Chat screen
    chatScreen: document.getElementById('chat-screen'),
    statusBar: document.getElementById('status-bar'),
    connectionStatus: document.getElementById('connection-status'),
    userInfo: document.getElementById('user-info'),
    messagesContainer: document.getElementById('messages-container'),
    messages: document.getElementById('messages'),
    loadMore: document.getElementById('load-more'),
    loadMoreBtn: document.getElementById('load-more-btn'),
    messageInput: document.getElementById('message-input'),
    sendBtn: document.getElementById('send-btn'),
    voiceBtn: document.getElementById('voice-btn'),
    logoutBtn: document.getElementById('logout-btn'),
    settingsBtn: document.getElementById('settings-btn'),

    // Settings panel
    settingsPanel: document.getElementById('settings-panel'),
    closeSettingsBtn: document.getElementById('close-settings-btn'),
    audioEnabledCheckbox: document.getElementById('audio-enabled'),
    wakeLockCheckbox: document.getElementById('wake-lock-enabled'),
    showTimestampsCheckbox: document.getElementById('show-timestamps'),
    accountUsername: document.getElementById('account-username'),
    logoutSettingsBtn: document.getElementById('logout-settings-btn'),

    // Loading
    loading: document.getElementById('loading')
};

/**
 * Initialize the application
 */
async function init() {
    console.log('Initializing GLaDOS Web Interface...');

    // Initialize login manager
    const savedServerUrl = localStorage.getItem('glados_server_url') || 'ws://localhost:8765';
    const apiBaseUrl = savedServerUrl.replace('ws://', 'http://').replace('wss://', 'https://').replace(':8765', ':8766');

    state.loginManager = new LoginManager(apiBaseUrl);

    if (savedServerUrl) {
        elements.serverUrl.value = savedServerUrl;
    }

    // Load settings
    state.audioEnabled = localStorage.getItem('audio_enabled') !== 'false';
    state.showTimestamps = localStorage.getItem('show_timestamps') !== 'false';
    elements.audioEnabledCheckbox.checked = state.audioEnabled;
    elements.showTimestampsCheckbox.checked = state.showTimestamps;

    // Setup event listeners
    elements.loginBtn.addEventListener('click', handleLogin);
    elements.usernameInput.addEventListener('keypress', (e) => {
        if (e.key === 'Enter') {
            e.preventDefault();
            elements.passwordInput.focus();
        }
    });
    elements.passwordInput.addEventListener('keypress', (e) => {
        if (e.key === 'Enter') {
            e.preventDefault();
            handleLogin();
        }
    });

    elements.sendBtn.addEventListener('click', sendMessage);
    elements.messageInput.addEventListener('keypress', (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            sendMessage();
        }
    });

    elements.voiceBtn.addEventListener('mousedown', startVoiceRecording);
    elements.voiceBtn.addEventListener('mouseup', stopVoiceRecording);
    elements.voiceBtn.addEventListener('touchstart', (e) => {
        e.preventDefault();
        startVoiceRecording();
    });
    elements.voiceBtn.addEventListener('touchend', (e) => {
        e.preventDefault();
        stopVoiceRecording();
    });

    elements.logoutBtn.addEventListener('click', handleLogout);
    elements.settingsBtn.addEventListener('click', showSettings);
    elements.closeSettingsBtn.addEventListener('click', hideSettings);
    elements.logoutSettingsBtn.addEventListener('click', handleLogout);

    elements.audioEnabledCheckbox.addEventListener('change', (e) => {
        state.audioEnabled = e.target.checked;
        localStorage.setItem('audio_enabled', state.audioEnabled);
    });

    elements.showTimestampsCheckbox.addEventListener('change', (e) => {
        state.showTimestamps = e.target.checked;
        localStorage.setItem('show_timestamps', state.showTimestamps);
        // Re-render messages
        renderMessages();
    });

    elements.wakeLockCheckbox.addEventListener('change', (e) => {
        if (e.target.checked) {
            requestWakeLock();
        } else {
            releaseWakeLock();
        }
    });

    elements.loadMoreBtn.addEventListener('click', loadMoreHistory);

    // Auto-login if saved credentials exist
    const savedAuth = state.loginManager.getSavedAuth();
    if (savedAuth && savedAuth.token) {
        console.log('Found saved credentials, attempting auto-login...');
        await autoLogin(savedAuth.token);
    }

    // Resume audio context on first user interaction
    document.addEventListener('click', resumeAudioContext, { once: true });
}

/**
 * Auto-login with saved token
 */
async function autoLogin(token) {
    const serverUrl = elements.serverUrl.value.trim();

    if (!serverUrl) {
        console.warn('No server URL configured');
        return;
    }

    // Save server URL
    localStorage.setItem('glados_server_url', serverUrl);

    // Connect to WebSocket with saved token
    connectWithToken(token, serverUrl);
}

/**
 * Handle login button click
 */
async function handleLogin() {
    const username = elements.usernameInput.value.trim();
    const password = elements.passwordInput.value.trim();
    const rememberMe = elements.rememberMeCheckbox.checked;
    const serverUrl = elements.serverUrl.value.trim();

    if (!username) {
        showLoginError('Please enter your username');
        return;
    }

    if (!password) {
        showLoginError('Please enter your password');
        return;
    }

    if (!serverUrl) {
        showLoginError('Please enter a server URL');
        return;
    }

    elements.loginError.textContent = '';
    elements.loginBtn.disabled = true;
    elements.loginBtn.textContent = 'Logging in...';

    try {
        // Attempt login
        const result = await state.loginManager.login(username, password, rememberMe);

        if (result.success) {
            console.log('Login successful:', result.user);

            // Save server URL
            localStorage.setItem('glados_server_url', serverUrl);

            // Connect to WebSocket with token
            connectWithToken(result.token, serverUrl);
        } else {
            showLoginError(result.error || 'Login failed');
            elements.loginBtn.disabled = false;
            elements.loginBtn.textContent = 'Log In';
        }
    } catch (error) {
        console.error('Login error:', error);
        showLoginError('Connection error. Please check your server URL.');
        elements.loginBtn.disabled = false;
        elements.loginBtn.textContent = 'Log In';
    }
}

/**
 * Connect to WebSocket with authentication token
 */
function connectWithToken(token, serverUrl) {
    // Create WebSocket connection
    state.ws = new GLaDOSWebSocket(serverUrl);

    // Setup event handlers
    state.ws.on('connected', () => {
        console.log('Connected to server');
    });

    state.ws.on('authenticated', (data) => {
        console.log('Authenticated:', data);
        state.currentUser = data;
        showChatScreen();
    });

    state.ws.on('auth_failed', (data) => {
        console.error('Authentication failed:', data);
        showLoginError(data.message || 'Authentication failed');
        elements.loginBtn.disabled = false;
        elements.loginBtn.textContent = 'Log In';

        // Clear invalid saved token
        state.loginManager.clearAuth();
    });

    state.ws.on('text', (data) => {
        console.log('Received text:', data.message);
        addMessage('glados', data.message, data.timestamp);
    });

    state.ws.on('audio', (data) => {
        console.log('Received audio');
        if (state.audioEnabled && state.audioPlayer) {
            state.audioPlayer.playAudio(data.data);
        }
    });

    state.ws.on('history_response', (data) => {
        console.log('Received history:', data.messages?.length || 0, 'messages');
        handleHistoryResponse(data);
    });

    state.ws.on('error', (data) => {
        console.error('WebSocket error:', data);
        showError(data.message || 'Connection error');
    });

    state.ws.on('disconnected', () => {
        console.log('Disconnected from server');
        updateConnectionStatus(false);
    });

    state.ws.on('reconnecting', (data) => {
        console.log('Reconnecting...', data);
        updateConnectionStatus(false, `Reconnecting (attempt ${data.attempt})...`);
    });

    // Connect
    state.ws.connect(token);
}

/**
 * Show chat screen after successful authentication
 */
function showChatScreen() {
    elements.loginScreen.style.display = 'none';
    elements.chatScreen.style.display = 'flex';

    // Update user info
    const username = state.currentUser.username || state.loginManager.getUser()?.username;
    elements.userInfo.textContent = username ? `@${username}` : `User #${state.currentUser.user_id}`;

    // Update account info in settings
    if (elements.accountUsername) {
        elements.accountUsername.textContent = username || `User #${state.currentUser.user_id}`;
    }

    // Initialize audio if enabled
    if (state.audioEnabled) {
        initializeAudio();
    }

    // Request wake lock if enabled
    if (elements.wakeLockCheckbox.checked) {
        requestWakeLock();
    }

    // Request conversation history
    state.ws.requestHistory(0, state.historyLimit);

    // Focus message input
    elements.messageInput.focus();

    updateConnectionStatus(true);
}

/**
 * Initialize audio capture and playback
 */
async function initializeAudio() {
    try {
        // Initialize audio capture
        state.audioCapture = new AudioCapture();
        const captureSuccess = await state.audioCapture.init();

        if (!captureSuccess) {
            console.warn('Failed to initialize audio capture');
            elements.voiceBtn.disabled = true;
            elements.voiceBtn.title = 'Microphone not available';
        }

        // Initialize audio player
        state.audioPlayer = new AudioPlayer();
        state.audioPlayer.init();

        console.log('Audio initialized');

    } catch (error) {
        console.error('Failed to initialize audio:', error);
        elements.voiceBtn.disabled = true;
    }
}

/**
 * Send a text message
 */
function sendMessage() {
    const text = elements.messageInput.value.trim();

    if (!text) {
        return;
    }

    if (!state.ws || !state.ws.isReady()) {
        showError('Not connected to server');
        return;
    }

    // Add message to UI immediately
    addMessage('user', text);

    // Send to server
    state.ws.sendText(text);

    // Clear input
    elements.messageInput.value = '';
}

/**
 * Start voice recording (push-to-talk)
 */
function startVoiceRecording() {
    if (!state.audioCapture || !state.audioEnabled) {
        return;
    }

    elements.voiceBtn.classList.add('recording');

    state.audioCapture.startRecording((audioData) => {
        // Convert and send audio data
        const base64Audio = float32ToBase64PCM(audioData);
        if (state.ws && state.ws.isReady()) {
            state.ws.sendAudio(base64Audio, 'pcm_s16le', 16000);
        }
    });
}

/**
 * Stop voice recording
 */
function stopVoiceRecording() {
    if (!state.audioCapture) {
        return;
    }

    elements.voiceBtn.classList.remove('recording');
    state.audioCapture.stopRecording();
}

/**
 * Add a message to the chat
 */
function addMessage(sender, text, timestamp = null) {
    const message = {
        sender: sender,
        text: text,
        timestamp: timestamp || new Date().toISOString()
    };

    state.messages.push(message);
    renderMessage(message);

    // Scroll to bottom
    scrollToBottom();
}

/**
 * Render a single message
 */
function renderMessage(message) {
    const messageEl = document.createElement('div');
    messageEl.className = `message ${message.sender}`;

    const headerEl = document.createElement('div');
    headerEl.className = 'message-header';

    const senderEl = document.createElement('span');
    senderEl.className = 'message-sender';
    senderEl.textContent = message.sender === 'user' ? 'You' : 'GLaDOS';
    headerEl.appendChild(senderEl);

    if (state.showTimestamps && message.timestamp) {
        const timestampEl = document.createElement('span');
        timestampEl.className = 'message-timestamp';
        timestampEl.textContent = formatTimestamp(message.timestamp);
        headerEl.appendChild(timestampEl);
    }

    const contentEl = document.createElement('div');
    contentEl.className = 'message-content';
    contentEl.textContent = message.text;

    messageEl.appendChild(headerEl);
    messageEl.appendChild(contentEl);

    elements.messages.appendChild(messageEl);
}

/**
 * Render all messages
 */
function renderMessages() {
    elements.messages.innerHTML = '';
    state.messages.forEach(message => renderMessage(message));
    scrollToBottom();
}

/**
 * Handle history response
 */
function handleHistoryResponse(data) {
    const messages = data.messages || [];
    state.hasMoreHistory = data.has_more || false;

    // Add messages to beginning of array
    messages.reverse().forEach(msg => {
        state.messages.unshift({
            sender: msg.role === 'user' ? 'user' : 'glados',
            text: msg.content,
            timestamp: msg.timestamp
        });
    });

    // Update offset
    state.historyOffset += messages.length;

    // Show/hide load more button
    elements.loadMore.style.display = state.hasMoreHistory ? 'block' : 'none';

    // Re-render all messages
    renderMessages();
}

/**
 * Load more history
 */
function loadMoreHistory() {
    if (!state.ws || !state.ws.isReady() || !state.hasMoreHistory) {
        return;
    }

    elements.loadMoreBtn.disabled = true;
    elements.loadMoreBtn.textContent = 'Loading...';

    state.ws.requestHistory(state.historyOffset, state.historyLimit);

    setTimeout(() => {
        elements.loadMoreBtn.disabled = false;
        elements.loadMoreBtn.textContent = 'Load earlier messages...';
    }, 1000);
}

/**
 * Format timestamp
 */
function formatTimestamp(timestamp) {
    const date = new Date(timestamp);
    const now = new Date();
    const diffMs = now - date;
    const diffMins = Math.floor(diffMs / 60000);

    if (diffMins < 1) {
        return 'just now';
    } else if (diffMins < 60) {
        return `${diffMins}m ago`;
    } else if (diffMins < 1440) {
        return `${Math.floor(diffMins / 60)}h ago`;
    } else {
        return date.toLocaleDateString();
    }
}

/**
 * Scroll to bottom of messages
 */
function scrollToBottom() {
    elements.messagesContainer.scrollTop = elements.messagesContainer.scrollHeight;
}

/**
 * Update connection status indicator
 */
function updateConnectionStatus(connected, statusText = null) {
    if (connected) {
        elements.connectionStatus.classList.remove('disconnected');
        elements.connectionStatus.classList.add('connected');
        elements.connectionStatus.querySelector('.status-text').textContent =
            statusText || 'Connected';
    } else {
        elements.connectionStatus.classList.remove('connected');
        elements.connectionStatus.classList.add('disconnected');
        elements.connectionStatus.querySelector('.status-text').textContent =
            statusText || 'Disconnected';
    }
}

/**
 * Handle logout button
 */
async function handleLogout() {
    // Call logout API
    try {
        await state.loginManager.logout();
    } catch (error) {
        console.error('Logout API error:', error);
        // Continue with logout even if API call fails
    }

    // Disconnect WebSocket
    if (state.ws) {
        state.ws.disconnect(true);
    }

    cleanup();

    // Return to login screen
    elements.chatScreen.style.display = 'none';
    elements.loginScreen.style.display = 'flex';
    elements.loginBtn.disabled = false;
    elements.loginBtn.textContent = 'Log In';

    // Clear messages
    state.messages = [];
    elements.messages.innerHTML = '';
    state.historyOffset = 0;

    // Clear form
    elements.passwordInput.value = '';

    // Focus username input
    elements.usernameInput.focus();

    // Hide settings if open
    hideSettings();
}

/**
 * Cleanup resources
 */
function cleanup() {
    if (state.audioCapture) {
        state.audioCapture.cleanup();
        state.audioCapture = null;
    }

    if (state.audioPlayer) {
        state.audioPlayer.cleanup();
        state.audioPlayer = null;
    }

    releaseWakeLock();
}

/**
 * Show settings panel
 */
function showSettings() {
    elements.settingsPanel.style.display = 'flex';
}

/**
 * Hide settings panel
 */
function hideSettings() {
    elements.settingsPanel.style.display = 'none';
}

/**
 * Show login error
 */
function showLoginError(message) {
    elements.loginError.textContent = message;
}

/**
 * Show error message
 */
function showError(message) {
    addMessage('system', `Error: ${message}`);
}

/**
 * Request wake lock to keep screen awake
 */
async function requestWakeLock() {
    if (!('wakeLock' in navigator)) {
        console.warn('Wake Lock API not supported');
        return;
    }

    try {
        state.wakeLock = await navigator.wakeLock.request('screen');
        console.log('Wake lock acquired');

        state.wakeLock.addEventListener('release', () => {
            console.log('Wake lock released');
        });
    } catch (error) {
        console.error('Failed to acquire wake lock:', error);
    }
}

/**
 * Release wake lock
 */
function releaseWakeLock() {
    if (state.wakeLock) {
        state.wakeLock.release();
        state.wakeLock = null;
    }
}

/**
 * Resume audio context (required by browser autoplay policy)
 */
function resumeAudioContext() {
    if (state.audioPlayer && state.audioPlayer.audioContext) {
        if (state.audioPlayer.audioContext.state === 'suspended') {
            state.audioPlayer.audioContext.resume();
        }
    }

    if (state.audioCapture && state.audioCapture.audioContext) {
        if (state.audioCapture.audioContext.state === 'suspended') {
            state.audioCapture.audioContext.resume();
        }
    }
}

/**
 * Register service worker for PWA support
 */
function registerServiceWorker() {
    if ('serviceWorker' in navigator) {
        window.addEventListener('load', () => {
            navigator.serviceWorker.register('/service-worker.js')
                .then(registration => {
                    console.log('Service Worker registered:', registration.scope);

                    // Check for updates
                    registration.addEventListener('updatefound', () => {
                        const newWorker = registration.installing;
                        console.log('Service Worker update found');

                        newWorker.addEventListener('statechange', () => {
                            if (newWorker.state === 'installed' && navigator.serviceWorker.controller) {
                                // New service worker available
                                console.log('New version available! Reload to update.');
                                // Could show notification to user here
                            }
                        });
                    });
                })
                .catch(error => {
                    console.error('Service Worker registration failed:', error);
                });
        });
    } else {
        console.log('Service Worker not supported in this browser');
    }
}

// Initialize app when DOM is ready
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => {
        init();
        registerServiceWorker();
    });
} else {
    init();
    registerServiceWorker();
}
