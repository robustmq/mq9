import {
  connect,
  NatsConnection,
  headers as natsHeaders,
  MsgHdrs,
} from "nats";

// ---------------------------------------------------------------------------
// Public types
// ---------------------------------------------------------------------------

export enum Priority {
  NORMAL = "normal",
  URGENT = "urgent",
  CRITICAL = "critical",
}

export interface Message {
  msgId: number;
  payload: Uint8Array;
  priority: Priority;
  createTime: number; // unix timestamp seconds
}

export interface SendOptions {
  priority?: Priority;
  key?: string;
  delay?: number;
  ttl?: number;
  tags?: string[];
}

export interface FetchOptions {
  groupName?: string;
  deliver?: "latest" | "earliest" | "from_time" | "from_id";
  fromTime?: number;
  fromId?: number;
  forceDeliver?: boolean;
  numMsgs?: number;
  maxWaitMs?: number;
}

export interface ConsumeOptions {
  groupName?: string;
  deliver?: "latest" | "earliest" | "from_time" | "from_id";
  numMsgs?: number;
  maxWaitMs?: number;
  autoAck?: boolean; // default true
  errorHandler?: (msg: Message, err: Error) => Promise<void>;
}

export interface DiscoverOptions {
  text?: string;
  semantic?: string;
  limit?: number;
  page?: number;
}

// ---------------------------------------------------------------------------
// Error
// ---------------------------------------------------------------------------

export class Mq9Error extends Error {
  constructor(message: string) {
    super(message);
    this.name = "Mq9Error";
    Object.setPrototypeOf(this, Mq9Error.prototype);
  }
}

// ---------------------------------------------------------------------------
// Consumer
// ---------------------------------------------------------------------------

export class Consumer {
  private _running = true;
  private _processedCount = 0;
  private _stopped: Promise<void>;
  private _resolve!: () => void;
  private _wakeResolve: (() => void) | null = null;

  constructor() {
    this._stopped = new Promise<void>((resolve) => {
      this._resolve = resolve;
    });
  }

  get isRunning(): boolean {
    return this._running;
  }

  get processedCount(): number {
    return this._processedCount;
  }

  /** @internal — called by the consume loop to increment the counter */
  _incrementProcessed(): void {
    this._processedCount++;
  }

  /** @internal — called by the consume loop when it exits */
  _markStopped(): void {
    this._running = false;
    this._resolve();
  }

  /** @internal — checked by the consume loop each iteration */
  _shouldStop(): boolean {
    return !this._running;
  }

  /**
   * @internal — sleep that can be interrupted by stop().
   * Resolves after `ms` milliseconds OR as soon as stop() is called.
   */
  async _interruptibleSleep(ms: number): Promise<void> {
    await new Promise<void>((resolve) => {
      this._wakeResolve = resolve;
      setTimeout(resolve, ms);
    });
    this._wakeResolve = null;
  }

  /** Signal the consumer loop to stop and wait for it to finish. */
  async stop(): Promise<void> {
    this._running = false;
    // Wake any sleeping interval immediately
    if (this._wakeResolve) {
      this._wakeResolve();
    }
    return this._stopped;
  }
}

// ---------------------------------------------------------------------------
// Wire-protocol helpers
// ---------------------------------------------------------------------------

function encodeRequest(payload: unknown): Uint8Array {
  return new TextEncoder().encode(JSON.stringify(payload));
}

function decodeResponse(data: Uint8Array): Record<string, unknown> {
  return JSON.parse(new TextDecoder().decode(data)) as Record<string, unknown>;
}

function checkError(resp: Record<string, unknown>): void {
  const err = resp["error"];
  if (typeof err === "string" && err !== "") {
    throw new Mq9Error(err);
  }
}

/** Decode a base64 string returned by the server into a Uint8Array. */
function decodeBase64(b64: string): Uint8Array {
  const buf = Buffer.from(b64, "base64");
  return new Uint8Array(buf.buffer, buf.byteOffset, buf.byteLength);
}

/** Normalise the payload that callers pass to send(). */
function normalisePayload(
  payload: Uint8Array | string | object
): Uint8Array {
  if (payload instanceof Uint8Array) {
    return payload;
  }
  if (typeof payload === "string") {
    return new TextEncoder().encode(payload);
  }
  return new TextEncoder().encode(JSON.stringify(payload));
}

// ---------------------------------------------------------------------------
// Mq9Client
// ---------------------------------------------------------------------------

export interface Mq9ClientOptions {
  requestTimeout?: number;   // ms, default 5000
  reconnectAttempts?: number; // default 10
  reconnectDelay?: number;    // ms, default 1000
}

export class Mq9Client {
  private readonly _server: string;
  private readonly _requestTimeout: number;
  private readonly _reconnectAttempts: number;
  private readonly _reconnectDelay: number;
  private _nc: NatsConnection | null = null;

  constructor(server: string, options: Mq9ClientOptions = {}) {
    this._server = server;
    this._requestTimeout = options.requestTimeout ?? 5000;
    this._reconnectAttempts = options.reconnectAttempts ?? 10;
    this._reconnectDelay = options.reconnectDelay ?? 1000;
  }

  // -------------------------------------------------------------------------
  // Lifecycle
  // -------------------------------------------------------------------------

  async connect(): Promise<void> {
    this._nc = await connect({
      servers: this._server,
      maxReconnectAttempts: this._reconnectAttempts,
      reconnectTimeWait: this._reconnectDelay,
    });
  }

  async close(): Promise<void> {
    if (this._nc && !this._nc.isClosed()) {
      await this._nc.drain();
    }
    this._nc = null;
  }

  // -------------------------------------------------------------------------
  // Internal helpers
  // -------------------------------------------------------------------------

  private _conn(): NatsConnection {
    if (!this._nc || this._nc.isClosed()) {
      throw new Mq9Error("Not connected — call connect() first");
    }
    return this._nc;
  }

  private async _request(
    subject: string,
    payload: unknown,
    hdrs?: MsgHdrs
  ): Promise<Record<string, unknown>> {
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

  async mailboxCreate(options: { name?: string; ttl?: number } = {}): Promise<string> {
    const body: Record<string, unknown> = {};
    if (options.name !== undefined) body["name"] = options.name;
    if (options.ttl !== undefined) body["ttl"] = options.ttl;

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

  async send(
    mailAddress: string,
    payload: Uint8Array | string | object,
    options: SendOptions = {}
  ): Promise<number> {
    const subject = `$mq9.AI.MSG.SEND.${mailAddress}`;
    const data = normalisePayload(payload);

    let hdrs: MsgHdrs | undefined;

    const needsHeaders =
      options.priority !== undefined ||
      options.key !== undefined ||
      options.delay !== undefined ||
      options.ttl !== undefined ||
      (options.tags !== undefined && options.tags.length > 0);

    if (needsHeaders) {
      hdrs = natsHeaders();
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

  async fetch(
    mailAddress: string,
    options: FetchOptions = {}
  ): Promise<Message[]> {
    const subject = `$mq9.AI.MSG.FETCH.${mailAddress}`;
    const body: Record<string, unknown> = {
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

    return rawMsgs.map((m: unknown) => {
      const raw = m as Record<string, unknown>;
      const b64 = raw["payload"] as string;
      return {
        msgId: raw["msg_id"] as number,
        payload: decodeBase64(b64),
        priority: (raw["priority"] as Priority) ?? Priority.NORMAL,
        createTime: raw["create_time"] as number,
      };
    });
  }

  async ack(
    mailAddress: string,
    groupName: string,
    msgId: number
  ): Promise<void> {
    const subject = `$mq9.AI.MSG.ACK.${mailAddress}`;
    const body = {
      group_name: groupName,
      mail_address: mailAddress,
      msg_id: msgId,
    };
    await this._request(subject, body);
  }

  async consume(
    mailAddress: string,
    handler: (msg: Message) => Promise<void>,
    options: ConsumeOptions = {}
  ): Promise<Consumer> {
    const autoAck = options.autoAck ?? true;
    const consumer = new Consumer();

    // Run the loop as a background async IIFE
    (async () => {
      while (!consumer._shouldStop()) {
        let messages: Message[];
        try {
          messages = await this.fetch(mailAddress, {
            groupName: options.groupName,
            deliver: options.deliver,
            numMsgs: options.numMsgs,
            maxWaitMs: options.maxWaitMs,
          });
        } catch (err) {
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
          if (consumer._shouldStop()) break;
          try {
            await handler(msg);
            if (autoAck && options.groupName) {
              await this.ack(mailAddress, options.groupName, msg.msgId);
            }
            consumer._incrementProcessed();
          } catch (err) {
            if (options.errorHandler) {
              try {
                await options.errorHandler(msg, err as Error);
              } catch (handlerErr) {
                console.error("[mq9] errorHandler threw:", handlerErr);
              }
            } else {
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

  async query(
    mailAddress: string,
    options: { key?: string; limit?: number; since?: number } = {}
  ): Promise<Message[]> {
    const subject = `$mq9.AI.MSG.QUERY.${mailAddress}`;
    const body: Record<string, unknown> = {};
    if (options.key !== undefined) body["key"] = options.key;
    if (options.limit !== undefined) body["limit"] = options.limit;
    if (options.since !== undefined) body["since"] = options.since;

    const resp = await this._request(subject, body);
    const rawMsgs = resp["messages"];
    if (!Array.isArray(rawMsgs)) {
      return [];
    }

    return rawMsgs.map((m: unknown) => {
      const raw = m as Record<string, unknown>;
      const b64 = raw["payload"] as string;
      return {
        msgId: raw["msg_id"] as number,
        payload: decodeBase64(b64),
        priority: (raw["priority"] as Priority) ?? Priority.NORMAL,
        createTime: raw["create_time"] as number,
      };
    });
  }

  async delete(mailAddress: string, msgId: number): Promise<void> {
    const subject = `$mq9.AI.MSG.DELETE.${mailAddress}.${msgId}`;
    await this._request(subject, {});
  }

  // -------------------------------------------------------------------------
  // Agent registry
  // -------------------------------------------------------------------------

  async agentRegister(agentCard: Record<string, unknown>): Promise<void> {
    if (!agentCard["mailbox"]) {
      throw new Mq9Error("agentCard must include a 'mailbox' field");
    }
    await this._request("$mq9.AI.AGENT.REGISTER", agentCard);
  }

  async agentUnregister(mailbox: string): Promise<void> {
    await this._request("$mq9.AI.AGENT.UNREGISTER", { mailbox });
  }

  async agentReport(report: Record<string, unknown>): Promise<void> {
    if (!report["mailbox"]) {
      throw new Mq9Error("report must include a 'mailbox' field");
    }
    await this._request("$mq9.AI.AGENT.REPORT", report);
  }

  async agentDiscover(
    options: DiscoverOptions = {}
  ): Promise<Record<string, unknown>[]> {
    const body: Record<string, unknown> = {};
    if (options.text !== undefined) body["text"] = options.text;
    if (options.semantic !== undefined) body["semantic"] = options.semantic;
    if (options.limit !== undefined) body["limit"] = options.limit;
    if (options.page !== undefined) body["page"] = options.page;

    const resp = await this._request("$mq9.AI.AGENT.DISCOVER", body);
    const agents = resp["agents"];
    if (!Array.isArray(agents)) {
      return [];
    }
    return agents as Record<string, unknown>[];
  }
}
