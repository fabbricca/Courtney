/**
 * GLaDOS WebSocket Connection Manager
 *
 * Manages WebSocket connection to the bridge server, handles
 * reconnection, and provides an event-based API for the app.
 */

export default class GLaDOSWebSocket {
    constructor(url) {
        this.url = url;
        this.ws = null;
        this.listeners = {};
        this.reconnectDelay = 1000;
        this.maxReconnectDelay = 30000;
        this.shouldReconnect = true;
        this.authenticated = false;
        this.connectionAttempts = 0;
    }

    /**
     * Connect to the WebSocket server and authenticate
     * @param {string} token - JWT authentication token
     */
    connect(token) {
        this.token = token;
        this.shouldReconnect = true;

        try {
            this.ws = new WebSocket(this.url);
            this.setupEventHandlers();
        } catch (error) {
            console.error('Failed to create WebSocket:', error);
            this.emit('error', { message: 'Failed to create WebSocket connection' });
        }
    }

    setupEventHandlers() {
        this.ws.onopen = () => {
            console.log('WebSocket connected');
            this.connectionAttempts = 0;
            this.reconnectDelay = 1000;

            // Send authentication message
            this.send({ type: 'auth', token: this.token });

            this.emit('connected');
        };

        this.ws.onmessage = (event) => {
            try {
                const msg = JSON.parse(event.data);
                console.log('Received:', msg.type);

                // Handle auth response
                if (msg.type === 'auth_response') {
                    if (msg.status === 'ok') {
                        this.authenticated = true;
                        this.emit('authenticated', {
                            user_id: msg.user_id,
                            username: msg.username
                        });
                    } else {
                        this.authenticated = false;
                        this.shouldReconnect = false;
                        this.emit('auth_failed', {
                            message: msg.message || 'Authentication failed'
                        });
                    }
                }

                // Emit message to listeners
                this.emit(msg.type, msg);
            } catch (error) {
                console.error('Failed to parse message:', error);
                this.emit('error', { message: 'Failed to parse server message' });
            }
        };

        this.ws.onerror = (error) => {
            console.error('WebSocket error:', error);
            this.emit('error', { message: 'WebSocket connection error' });
        };

        this.ws.onclose = (event) => {
            console.log('WebSocket disconnected:', event.code, event.reason);
            this.authenticated = false;
            this.emit('disconnected', { code: event.code, reason: event.reason });

            if (this.shouldReconnect) {
                this.scheduleReconnect();
            }
        };
    }

    scheduleReconnect() {
        this.connectionAttempts++;
        const delay = Math.min(
            this.reconnectDelay * Math.pow(1.5, this.connectionAttempts - 1),
            this.maxReconnectDelay
        );

        console.log(`Reconnecting in ${delay}ms... (attempt ${this.connectionAttempts})`);
        this.emit('reconnecting', { delay, attempt: this.connectionAttempts });

        setTimeout(() => {
            if (this.shouldReconnect && this.token) {
                this.connect(this.token);
            }
        }, delay);
    }

    /**
     * Send a message to the server
     * @param {Object} message - Message object with 'type' field
     */
    send(message) {
        if (this.ws && this.ws.readyState === WebSocket.OPEN) {
            try {
                this.ws.send(JSON.stringify(message));
                return true;
            } catch (error) {
                console.error('Failed to send message:', error);
                this.emit('error', { message: 'Failed to send message' });
                return false;
            }
        } else {
            console.warn('WebSocket not connected, cannot send message');
            return false;
        }
    }

    /**
     * Send text message to GLaDOS
     * @param {string} text - Message text
     */
    sendText(text) {
        return this.send({ type: 'text', message: text });
    }

    /**
     * Send audio data to GLaDOS
     * @param {string} audioData - Base64 encoded audio
     * @param {string} format - Audio format (default: pcm_s16le)
     * @param {number} sampleRate - Sample rate (default: 16000)
     */
    sendAudio(audioData, format = 'pcm_s16le', sampleRate = 16000) {
        return this.send({
            type: 'audio',
            data: audioData,
            format: format,
            sampleRate: sampleRate
        });
    }

    /**
     * Request conversation history
     * @param {number} offset - Offset for pagination
     * @param {number} limit - Number of messages to fetch
     */
    requestHistory(offset = 0, limit = 50) {
        return this.send({
            type: 'history_request',
            offset: offset,
            limit: limit
        });
    }

    /**
     * Disconnect from the server
     * @param {boolean} permanent - If true, don't reconnect
     */
    disconnect(permanent = false) {
        this.shouldReconnect = !permanent;

        if (this.ws) {
            this.ws.close(1000, 'Client disconnecting');
            this.ws = null;
        }
    }

    /**
     * Register an event listener
     * @param {string} event - Event name
     * @param {Function} callback - Callback function
     */
    on(event, callback) {
        if (!this.listeners[event]) {
            this.listeners[event] = [];
        }
        this.listeners[event].push(callback);
    }

    /**
     * Unregister an event listener
     * @param {string} event - Event name
     * @param {Function} callback - Callback function to remove
     */
    off(event, callback) {
        if (this.listeners[event]) {
            this.listeners[event] = this.listeners[event].filter(cb => cb !== callback);
        }
    }

    /**
     * Emit an event to all registered listeners
     * @param {string} event - Event name
     * @param {*} data - Event data
     */
    emit(event, data) {
        if (this.listeners[event]) {
            this.listeners[event].forEach(callback => {
                try {
                    callback(data);
                } catch (error) {
                    console.error(`Error in ${event} listener:`, error);
                }
            });
        }
    }

    /**
     * Get connection status
     * @returns {string} Connection status
     */
    getStatus() {
        if (!this.ws) return 'disconnected';

        switch (this.ws.readyState) {
            case WebSocket.CONNECTING:
                return 'connecting';
            case WebSocket.OPEN:
                return this.authenticated ? 'authenticated' : 'connected';
            case WebSocket.CLOSING:
                return 'closing';
            case WebSocket.CLOSED:
                return 'disconnected';
            default:
                return 'unknown';
        }
    }

    /**
     * Check if connected and authenticated
     * @returns {boolean}
     */
    isReady() {
        return this.ws &&
               this.ws.readyState === WebSocket.OPEN &&
               this.authenticated;
    }
}
