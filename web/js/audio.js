/**
 * GLaDOS Audio Manager
 *
 * Handles microphone input and audio playback using Web Audio API
 */

export class AudioCapture {
    constructor() {
        this.audioContext = null;
        this.mediaStream = null;
        this.processor = null;
        this.source = null;
        this.isRecording = false;
        this.onAudioData = null;
    }

    /**
     * Initialize audio capture
     * @returns {Promise<boolean>} Success status
     */
    async init() {
        try {
            // Request microphone access
            this.mediaStream = await navigator.mediaDevices.getUserMedia({
                audio: {
                    echoCancellation: true,
                    noiseSuppression: true,
                    autoGainControl: true,
                    sampleRate: 16000
                }
            });

            // Create audio context
            this.audioContext = new (window.AudioContext || window.webkitAudioContext)({
                sampleRate: 16000
            });

            // Create source and processor
            this.source = this.audioContext.createMediaStreamSource(this.mediaStream);
            this.processor = this.audioContext.createScriptProcessor(4096, 1, 1);

            // Connect nodes
            this.source.connect(this.processor);
            this.processor.connect(this.audioContext.destination);

            // Handle audio processing
            this.processor.onaudioprocess = (e) => {
                if (this.isRecording && this.onAudioData) {
                    const audioData = e.inputBuffer.getChannelData(0);
                    this.onAudioData(audioData);
                }
            };

            console.log('Audio capture initialized');
            return true;

        } catch (error) {
            console.error('Failed to initialize audio capture:', error);
            return false;
        }
    }

    /**
     * Start recording audio
     * @param {Function} callback - Called with audio data chunks
     */
    startRecording(callback) {
        if (!this.audioContext) {
            console.error('Audio context not initialized');
            return false;
        }

        // Resume audio context if suspended (required by browser autoplay policy)
        if (this.audioContext.state === 'suspended') {
            this.audioContext.resume();
        }

        this.isRecording = true;
        this.onAudioData = callback;
        console.log('Recording started');
        return true;
    }

    /**
     * Stop recording audio
     */
    stopRecording() {
        this.isRecording = false;
        this.onAudioData = null;
        console.log('Recording stopped');
    }

    /**
     * Clean up resources
     */
    cleanup() {
        this.stopRecording();

        if (this.processor) {
            this.processor.disconnect();
            this.processor = null;
        }

        if (this.source) {
            this.source.disconnect();
            this.source = null;
        }

        if (this.mediaStream) {
            this.mediaStream.getTracks().forEach(track => track.stop());
            this.mediaStream = null;
        }

        if (this.audioContext) {
            this.audioContext.close();
            this.audioContext = null;
        }

        console.log('Audio capture cleaned up');
    }

    /**
     * Check if microphone is available
     * @returns {Promise<boolean>}
     */
    static async checkMicrophoneAvailable() {
        try {
            const devices = await navigator.mediaDevices.enumerateDevices();
            return devices.some(device => device.kind === 'audioinput');
        } catch (error) {
            console.error('Failed to check microphone:', error);
            return false;
        }
    }
}

export class AudioPlayer {
    constructor() {
        this.audioContext = null;
        this.playQueue = [];
        this.isPlaying = false;
        this.onPlaybackStart = null;
        this.onPlaybackEnd = null;
    }

    /**
     * Initialize audio player
     */
    init() {
        if (!this.audioContext) {
            this.audioContext = new (window.AudioContext || window.webkitAudioContext)();
            console.log('Audio player initialized');
        }
    }

    /**
     * Play audio from base64 encoded data
     * @param {string} base64Audio - Base64 encoded audio data
     * @returns {Promise<void>}
     */
    async playAudio(base64Audio) {
        if (!this.audioContext) {
            this.init();
        }

        try {
            // Resume audio context if needed
            if (this.audioContext.state === 'suspended') {
                await this.audioContext.resume();
            }

            // Decode base64 to array buffer
            const arrayBuffer = this.base64ToArrayBuffer(base64Audio);

            // Decode audio data
            const audioBuffer = await this.audioContext.decodeAudioData(arrayBuffer);

            // Add to queue
            this.playQueue.push(audioBuffer);

            // Start playback if not already playing
            if (!this.isPlaying) {
                this.playNext();
            }

        } catch (error) {
            console.error('Failed to play audio:', error);
        }
    }

    /**
     * Play the next audio buffer in the queue
     */
    playNext() {
        if (this.playQueue.length === 0) {
            this.isPlaying = false;
            if (this.onPlaybackEnd) {
                this.onPlaybackEnd();
            }
            return;
        }

        this.isPlaying = true;

        if (this.onPlaybackStart) {
            this.onPlaybackStart();
        }

        const buffer = this.playQueue.shift();
        const source = this.audioContext.createBufferSource();
        source.buffer = buffer;
        source.connect(this.audioContext.destination);

        source.onended = () => {
            this.playNext();
        };

        source.start(0);
        console.log('Playing audio');
    }

    /**
     * Stop playback and clear queue
     */
    stop() {
        this.playQueue = [];
        this.isPlaying = false;
        console.log('Audio playback stopped');
    }

    /**
     * Convert base64 string to ArrayBuffer
     * @param {string} base64 - Base64 encoded string
     * @returns {ArrayBuffer}
     */
    base64ToArrayBuffer(base64) {
        const binary = atob(base64);
        const bytes = new Uint8Array(binary.length);
        for (let i = 0; i < binary.length; i++) {
            bytes[i] = binary.charCodeAt(i);
        }
        return bytes.buffer;
    }

    /**
     * Clean up resources
     */
    cleanup() {
        this.stop();

        if (this.audioContext) {
            this.audioContext.close();
            this.audioContext = null;
        }

        console.log('Audio player cleaned up');
    }
}

/**
 * Convert Float32Array to base64 encoded PCM
 * @param {Float32Array} float32Array - Audio data
 * @returns {string} Base64 encoded audio
 */
export function float32ToBase64PCM(float32Array) {
    // Convert float32 (-1 to 1) to int16 PCM
    const int16Array = new Int16Array(float32Array.length);
    for (let i = 0; i < float32Array.length; i++) {
        const s = Math.max(-1, Math.min(1, float32Array[i]));
        int16Array[i] = s < 0 ? s * 0x8000 : s * 0x7FFF;
    }

    // Convert to base64
    const bytes = new Uint8Array(int16Array.buffer);
    let binary = '';
    for (let i = 0; i < bytes.length; i++) {
        binary += String.fromCharCode(bytes[i]);
    }
    return btoa(binary);
}
