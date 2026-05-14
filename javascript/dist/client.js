"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.Mq9Client = exports.Consumer = exports.Mq9Error = exports.Priority = void 0;
const nats_1 = require("nats");
// ---------------------------------------------------------------------------
// Public types
// ---------------------------------------------------------------------------
var Priority;
(function (Priority) {
    Priority["NORMAL"] = "normal";
    Priority["URGENT"] = "urgent";
    Priority["CRITICAL"] = "critical";
})(Priority || (exports.Priority = Priority = {}));
// ---------------------------------------------------------------------------
// Error
// ---------------------------------------------------------------------------
class Mq9Error extends Error {
    constructor(message) {
        super(message);
        this.name = "Mq9Error";
        Object.setPrototypeOf(this, Mq9Error.prototype);
    }
}
exports.Mq9Error = Mq9Error;
// ---------------------------------------------------------------------------
// Consumer
// ---------------------------------------------------------------------------
class Consumer {
    constructor() {
        this._running = true;
        this._processedCount = 0;
        this._wakeResolve = null;
        this._stopped = new Promise((resolve) => {
            this._resolve = resolve;
        });
    }
    get isRunning() {
        return this._running;
    }
    get processedCount() {
        return this._processedCount;
    }
    /** @internal — called by the consume loop to increment the counter */
    _incrementProcessed() {
        this._processedCount++;
    }
    /** @internal — called by the consume loop when it exits */
    _markStopped() {
        this._running = false;
        this._resolve();
    }
    /** @internal — checked by the consume loop each iteration */
    _shouldStop() {
        return !this._running;
    }
    /**
     * @internal — sleep that can be interrupted by stop().
     * Resolves after `ms` milliseconds OR as soon as stop() is called.
     */
    async _interruptibleSleep(ms) {
        await new Promise((resolve) => {
            this._wakeResolve = resolve;
            setTimeout(resolve, ms);
        });
        this._wakeResolve = null;
    }
    /** Signal the consumer loop to stop and wait for it to finish. */
    async stop() {
        this._running = false;
        // Wake any sleeping interval immediately
        if (this._wakeResolve) {
            this._wakeResolve();
        }
        return this._stopped;
    }
}
exports.Consumer = Consumer;
// ---------------------------------------------------------------------------
// Wire-protocol helpers
// ---------------------------------------------------------------------------
function encodeRequest(payload) {
    return new TextEncoder().encode(JSON.stringify(payload));
}
function decodeResponse(data) {
    return JSON.parse(new TextDecoder().decode(data));
}
function checkError(resp) {
    const err = resp["error"];
    if (typeof err === "string" && err !== "") {
        throw new Mq9Error(err);
    }
}
/** Decode a base64 string returned by the server into a Uint8Array. */
function decodeBase64(b64) {
    const buf = Buffer.from(b64, "base64");
    return new Uint8Array(buf.buffer, buf.byteOffset, buf.byteLength);
}
/** Normalise the payload that callers pass to send(). */
function normalisePayload(payload) {
    if (payload instanceof Uint8Array) {
        return payload;
    }
    if (typeof payload === "string") {
        return new TextEncoder().encode(payload);
    }
    return new TextEncoder().encode(JSON.stringify(payload));
}
class Mq9Client {
    constructor(server, options = {}) {
        this._nc = null;
        this._server = server;
        this._requestTimeout = options.requestTimeout ?? 5000;
        this._reconnectAttempts = options.reconnectAttempts ?? 10;
        this._reconnectDelay = options.reconnectDelay ?? 1000;
    }
    // -------------------------------------------------------------------------
    // Lifecycle
    // -------------------------------------------------------------------------
    async connect() {
        this._nc = await (0, nats_1.connect)({
            servers: this._server,
            maxReconnectAttempts: this._reconnectAttempts,
            reconnectTimeWait: this._reconnectDelay,
        });
    }
    async close() {
        if (this._nc && !this._nc.isClosed()) {
            await this._nc.drain();
        }
        this._nc = null;
    }
    // -------------------------------------------------------------------------
    // Internal helpers
    // -------------------------------------------------------------------------
    _conn() {
        if (!this._nc || this._nc.isClosed()) {
            throw new Mq9Error("Not connected — call connect() first");
        }
        return this._nc;
    }
    async _request(subject, payload, hdrs) {
        const nc = this._conn();
        const data = encodeRequest(payload);
        const msg = await nc.request(subject, data, {
            timeout: this._requestTimeout,
            headers: hdrs,
        });
        const resp = decodeResponse(msg.data);
        checkError(resp);
        return resp;
    }
    // -------------------------------------------------------------------------
    // Mailbox
    // -------------------------------------------------------------------------
    async mailboxCreate(options = {}) {
        const body = {};
        if (options.name !== undefined)
            body["name"] = options.name;
        if (options.ttl !== undefined)
            body["ttl"] = options.ttl;
        const resp = await this._request("$mq9.AI.MAILBOX.CREATE", body);
        const addr = resp["mail_address"];
        if (typeof addr !== "string") {
            throw new Mq9Error("Invalid response: missing mail_address");
        }
        return addr;
    }
    // -------------------------------------------------------------------------
    // Messaging
    // -------------------------------------------------------------------------
    async send(mailAddress, payload, options = {}) {
        const subject = `$mq9.AI.MSG.SEND.${mailAddress}`;
        const data = normalisePayload(payload);
        let hdrs;
        const needsHeaders = options.priority !== undefined ||
            options.key !== undefined ||
            options.delay !== undefined ||
            options.ttl !== undefined ||
            (options.tags !== undefined && options.tags.length > 0);
        if (needsHeaders) {
            hdrs = (0, nats_1.headers)();
            if (options.priority !== undefined) {
                hdrs.set("mq9-priority", options.priority);
            }
            if (options.key !== undefined) {
                hdrs.set("mq9-key", options.key);
            }
            if (options.delay !== undefined) {
                hdrs.set("mq9-delay", String(options.delay));
            }
            if (options.ttl !== undefined) {
                hdrs.set("mq9-ttl", String(options.ttl));
            }
            if (options.tags !== undefined && options.tags.length > 0) {
                hdrs.set("mq9-tags", options.tags.join(","));
            }
        }
        const nc = this._conn();
        const msg = await nc.request(subject, data, {
            timeout: this._requestTimeout,
            headers: hdrs,
        });
        const resp = decodeResponse(msg.data);
        checkError(resp);
        const msgId = resp["msg_id"];
        if (typeof msgId !== "number") {
            throw new Mq9Error("Invalid response: missing msg_id");
        }
        return msgId;
    }
    async fetch(mailAddress, options = {}) {
        const subject = `$mq9.AI.MSG.FETCH.${mailAddress}`;
        const body = {
            group_name: options.groupName ?? "",
            deliver: options.deliver ?? "latest",
            from_time: options.fromTime ?? 0,
            from_id: options.fromId ?? 0,
            force_deliver: options.forceDeliver ?? false,
            config: {
                num_msgs: options.numMsgs ?? 100,
                max_wait_ms: options.maxWaitMs ?? 500,
            },
        };
        const resp = await this._request(subject, body);
        const rawMsgs = resp["messages"];
        if (!Array.isArray(rawMsgs)) {
            return [];
        }
        return rawMsgs.map((m) => {
            const raw = m;
            const b64 = raw["payload"];
            return {
                msgId: raw["msg_id"],
                payload: decodeBase64(b64),
                priority: raw["priority"] ?? Priority.NORMAL,
                createTime: raw["create_time"],
            };
        });
    }
    async ack(mailAddress, groupName, msgId) {
        const subject = `$mq9.AI.MSG.ACK.${mailAddress}`;
        const body = {
            group_name: groupName,
            mail_address: mailAddress,
            msg_id: msgId,
        };
        await this._request(subject, body);
    }
    async consume(mailAddress, handler, options = {}) {
        const autoAck = options.autoAck ?? true;
        const consumer = new Consumer();
        // Run the loop as a background async IIFE
        (async () => {
            while (!consumer._shouldStop()) {
                let messages;
                try {
                    messages = await this.fetch(mailAddress, {
                        groupName: options.groupName,
                        deliver: options.deliver,
                        numMsgs: options.numMsgs,
                        maxWaitMs: options.maxWaitMs,
                    });
                }
                catch (err) {
                    console.error("[mq9] fetch error:", err);
                    // Wait before retrying (interruptible so stop() resolves quickly)
                    await consumer._interruptibleSleep(1000);
                    continue;
                }
                if (messages.length === 0) {
                    // No messages — yield briefly to prevent busy-spin (interruptible)
                    await consumer._interruptibleSleep(50);
                    continue;
                }
                for (const msg of messages) {
                    if (consumer._shouldStop())
                        break;
                    try {
                        await handler(msg);
                        if (autoAck && options.groupName) {
                            await this.ack(mailAddress, options.groupName, msg.msgId);
                        }
                        consumer._incrementProcessed();
                    }
                    catch (err) {
                        if (options.errorHandler) {
                            try {
                                await options.errorHandler(msg, err);
                            }
                            catch (handlerErr) {
                                console.error("[mq9] errorHandler threw:", handlerErr);
                            }
                        }
                        else {
                            console.error("[mq9] handler error for msg", msg.msgId, ":", err);
                        }
                        // Do not ack, do not increment processedCount
                    }
                }
            }
            consumer._markStopped();
        })();
        return consumer;
    }
    async query(mailAddress, options = {}) {
        const subject = `$mq9.AI.MSG.QUERY.${mailAddress}`;
        const body = {};
        if (options.key !== undefined)
            body["key"] = options.key;
        if (options.limit !== undefined)
            body["limit"] = options.limit;
        if (options.since !== undefined)
            body["since"] = options.since;
        const resp = await this._request(subject, body);
        const rawMsgs = resp["messages"];
        if (!Array.isArray(rawMsgs)) {
            return [];
        }
        return rawMsgs.map((m) => {
            const raw = m;
            const b64 = raw["payload"];
            return {
                msgId: raw["msg_id"],
                payload: decodeBase64(b64),
                priority: raw["priority"] ?? Priority.NORMAL,
                createTime: raw["create_time"],
            };
        });
    }
    async delete(mailAddress, msgId) {
        const subject = `$mq9.AI.MSG.DELETE.${mailAddress}.${msgId}`;
        await this._request(subject, {});
    }
    // -------------------------------------------------------------------------
    // Agent registry
    // -------------------------------------------------------------------------
    async agentRegister(agentCard) {
        if (!agentCard["mailbox"]) {
            throw new Mq9Error("agentCard must include a 'mailbox' field");
        }
        await this._request("$mq9.AI.AGENT.REGISTER", agentCard);
    }
    async agentUnregister(mailbox) {
        await this._request("$mq9.AI.AGENT.UNREGISTER", { mailbox });
    }
    async agentReport(report) {
        if (!report["mailbox"]) {
            throw new Mq9Error("report must include a 'mailbox' field");
        }
        await this._request("$mq9.AI.AGENT.REPORT", report);
    }
    async agentDiscover(options = {}) {
        const body = {};
        if (options.text !== undefined)
            body["text"] = options.text;
        if (options.semantic !== undefined)
            body["semantic"] = options.semantic;
        if (options.limit !== undefined)
            body["limit"] = options.limit;
        if (options.page !== undefined)
            body["page"] = options.page;
        const resp = await this._request("$mq9.AI.AGENT.DISCOVER", body);
        const agents = resp["agents"];
        if (!Array.isArray(agents)) {
            return [];
        }
        return agents;
    }
}
exports.Mq9Client = Mq9Client;
//# sourceMappingURL=client.js.map