export declare enum Priority {
    NORMAL = "normal",
    URGENT = "urgent",
    CRITICAL = "critical"
}
export interface Message {
    msgId: number;
    payload: Uint8Array;
    priority: Priority;
    createTime: number;
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
    autoAck?: boolean;
    errorHandler?: (msg: Message, err: Error) => Promise<void>;
}
export interface DiscoverOptions {
    text?: string;
    semantic?: string;
    limit?: number;
    page?: number;
}
export declare class Mq9Error extends Error {
    constructor(message: string);
}
export declare class Consumer {
    private _running;
    private _processedCount;
    private _stopped;
    private _resolve;
    private _wakeResolve;
    constructor();
    get isRunning(): boolean;
    get processedCount(): number;
    /** @internal — called by the consume loop to increment the counter */
    _incrementProcessed(): void;
    /** @internal — called by the consume loop when it exits */
    _markStopped(): void;
    /** @internal — checked by the consume loop each iteration */
    _shouldStop(): boolean;
    /**
     * @internal — sleep that can be interrupted by stop().
     * Resolves after `ms` milliseconds OR as soon as stop() is called.
     */
    _interruptibleSleep(ms: number): Promise<void>;
    /** Signal the consumer loop to stop and wait for it to finish. */
    stop(): Promise<void>;
}
export interface Mq9ClientOptions {
    requestTimeout?: number;
    reconnectAttempts?: number;
    reconnectDelay?: number;
}
export declare class Mq9Client {
    private readonly _server;
    private readonly _requestTimeout;
    private readonly _reconnectAttempts;
    private readonly _reconnectDelay;
    private _nc;
    constructor(server: string, options?: Mq9ClientOptions);
    connect(): Promise<void>;
    close(): Promise<void>;
    private _conn;
    private _request;
    mailboxCreate(options?: {
        name?: string;
        ttl?: number;
    }): Promise<string>;
    send(mailAddress: string, payload: Uint8Array | string | object, options?: SendOptions): Promise<number>;
    fetch(mailAddress: string, options?: FetchOptions): Promise<Message[]>;
    ack(mailAddress: string, groupName: string, msgId: number): Promise<void>;
    consume(mailAddress: string, handler: (msg: Message) => Promise<void>, options?: ConsumeOptions): Promise<Consumer>;
    query(mailAddress: string, options?: {
        key?: string;
        limit?: number;
        since?: number;
    }): Promise<Message[]>;
    delete(mailAddress: string, msgId: number): Promise<void>;
    agentRegister(agentCard: Record<string, unknown>): Promise<void>;
    agentUnregister(mailbox: string): Promise<void>;
    agentReport(report: Record<string, unknown>): Promise<void>;
    agentDiscover(options?: DiscoverOptions): Promise<Record<string, unknown>[]>;
}
//# sourceMappingURL=client.d.ts.map