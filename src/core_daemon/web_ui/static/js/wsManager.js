/**
 * wsManager.js - Centralized WebSocket manager for rvc2api Web UI
 *
 * Provides a reusable WebSocketManager class for robust connection, reconnection,
 * message dispatch, and teardown for any WebSocket endpoint (lights, logs, CAN sniffer, etc).
 *
 * Author: Ryan Holt
 * Last updated: 2025-05-12
 */

export class WebSocketManager {
  /**
   * @param {string} url - The WebSocket URL.
   * @param {function} onMessage - Handler for incoming messages (event.data).
   * @param {object} [options]
   * @param {function} [options.onOpen] - Handler for open event.
   * @param {function} [options.onClose] - Handler for close event.
   * @param {function} [options.onError] - Handler for error event.
   * @param {boolean} [options.autoReconnect=true] - Whether to auto-reconnect.
   * @param {number} [options.reconnectInterval=5000] - Reconnect interval in ms.
   * @param {number} [options.maxRetries=Infinity] - Max reconnect attempts.
   */
  constructor(url, onMessage, options = {}) {
    this.url = url;
    this.onMessage = onMessage;
    this.onOpen = options.onOpen || (() => {});
    this.onClose = options.onClose || (() => {});
    this.onError = options.onError || (() => {});
    this.autoReconnect = options.autoReconnect !== false;
    this.reconnectInterval = options.reconnectInterval || 5000;
    this.maxRetries = options.maxRetries || Infinity;
    this._retries = 0;
    this._shouldReconnect = true;
    this._ws = null;
    this.connect();
  }

  connect() {
    this._ws = new window.WebSocket(this.url);
    this._ws.onopen = (event) => {
      this._retries = 0;
      this.onOpen(event);
    };
    this._ws.onmessage = (event) => {
      this.onMessage(event.data, event);
    };
    this._ws.onerror = (event) => {
      this.onError(event);
    };
    this._ws.onclose = (event) => {
      this.onClose(event);
      if (
        this.autoReconnect &&
        this._shouldReconnect &&
        this._retries < this.maxRetries
      ) {
        setTimeout(() => {
          this._retries++;
          this.connect();
        }, this.reconnectInterval);
      }
    };
  }

  send(data) {
    if (this._ws && this._ws.readyState === window.WebSocket.OPEN) {
      this._ws.send(data);
    }
  }

  close() {
    this._shouldReconnect = false;
    if (this._ws) {
      this._ws.close();
    }
  }

  isOpen() {
    return this._ws && this._ws.readyState === window.WebSocket.OPEN;
  }
}
