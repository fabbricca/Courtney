/**
 * Login Handler for GLaDOS Web Interface
 * Handles username/password authentication
 */

export class LoginManager {
    constructor() {
        this.apiBaseUrl = null;
        this.token = null;
        this.user = null;
    }

    /**
     * Initialize login manager with server URL
     */
    init(serverUrl) {
        // Extract host/port from WebSocket URL and convert to HTTP
        const wsUrl = new URL(serverUrl);
        const protocol = wsUrl.protocol === 'wss:' ? 'https:' : 'http:';

        // API runs on port 8766 (health check port)
        const apiPort = 8766;
        this.apiBaseUrl = `${protocol}//${wsUrl.hostname}:${apiPort}`;

        console.log('Login API URL:', this.apiBaseUrl);

        // Check for saved token
        const savedToken = this.getSavedToken();
        if (savedToken) {
            this.token = savedToken.token;
            this.user = savedToken.user;
        }
    }

    /**
     * Attempt to log in with username and password
     */
    async login(username, password, rememberMe = false) {
        try {
            const response = await fetch(`${this.apiBaseUrl}/api/login`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    username,
                    password
                })
            });

            const data = await response.json();

            if (!response.ok || !data.success) {
                throw new Error(data.error || 'Login failed');
            }

            // Save token and user info
            this.token = data.token;
            this.user = data.user;

            // Save to localStorage if "remember me" is checked
            if (rememberMe) {
                this.saveToken(data.token, data.user);
            }

            console.log('Login successful:', this.user.username);
            return {
                success: true,
                token: this.token,
                user: this.user
            };

        } catch (error) {
            console.error('Login error:', error);
            return {
                success: false,
                error: error.message
            };
        }
    }

    /**
     * Log out the current user
     */
    async logout() {
        try {
            if (this.token) {
                // Call logout API
                await fetch(`${this.apiBaseUrl}/api/logout`, {
                    method: 'POST',
                    headers: {
                        'Authorization': `Bearer ${this.token}`
                    }
                });
            }
        } catch (error) {
            console.error('Logout error:', error);
        } finally {
            // Clear local state
            this.token = null;
            this.user = null;
            this.clearSavedToken();
        }
    }

    /**
     * Get the current authentication token
     */
    getToken() {
        return this.token;
    }

    /**
     * Get the current user
     */
    getUser() {
        return this.user;
    }

    /**
     * Check if user is logged in
     */
    isLoggedIn() {
        return this.token !== null && this.user !== null;
    }

    /**
     * Save token to localStorage
     */
    saveToken(token, user) {
        try {
            localStorage.setItem('glados_auth', JSON.stringify({
                token,
                user,
                timestamp: Date.now()
            }));
        } catch (error) {
            console.error('Failed to save token:', error);
        }
    }

    /**
     * Get saved token from localStorage
     */
    getSavedToken() {
        try {
            const saved = localStorage.getItem('glados_auth');
            if (!saved) return null;

            const data = JSON.parse(saved);

            // Check if token is less than 7 days old
            const maxAge = 7 * 24 * 60 * 60 * 1000; // 7 days
            if (Date.now() - data.timestamp > maxAge) {
                this.clearSavedToken();
                return null;
            }

            return data;
        } catch (error) {
            console.error('Failed to load saved token:', error);
            return null;
        }
    }

    /**
     * Clear saved token from localStorage
     */
    clearSavedToken() {
        try {
            localStorage.removeItem('glados_auth');
        } catch (error) {
            console.error('Failed to clear token:', error);
        }
    }
}
