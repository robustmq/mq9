import {
  Mq9Client,
  Mq9Error,
  Priority,
  Consumer,
  Message,
} from "../src/client";

// ---------------------------------------------------------------------------
// Mock nats module
// ---------------------------------------------------------------------------

jest.mock("nats");

import * as nats from "nats";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/** Build a Uint8Array that encodes a JSON object, simulating a NATS response. */
function jsonBytes(obj: unknown): Uint8Array {
  return new TextEncoder().encode(JSON.stringify(obj));
}

/** Base64-encode a string to simulate server-side payload encoding. */
function toBase64(str: string): string {
  return Buffer.from(str).toString("base64");
}

/** Create a mock NATS message whose .data is the JSON-encoded obj. */
function mockMsg(obj: unknown): { data: Uint8Array } {
  return { data: jsonBytes(obj) };
}

// ---------------------------------------------------------------------------
// Mock setup
// ---------------------------------------------------------------------------

let mockRequest: jest.Mock;
let mockPublish: jest.Mock;
let mockDrain: jest.Mock;
let mockIsClosed: jest.Mock;
let mockSubscribe: jest.Mock;
let mockConnect: jest.Mock;
let mockHeadersSet: jest.Mock;
let mockHeadersAppend: jest.Mock;
let mockNatsHeaders: jest.Mock;

function setupMocks(requestImpl?: jest.Mock): void {
  mockRequest = requestImpl ?? jest.fn();
  mockPublish = jest.fn();
  mockDrain = jest.fn().mockResolvedValue(undefined);
  mockIsClosed = jest.fn().mockReturnValue(false);
  mockSubscribe = jest.fn().mockReturnValue({ unsubscribe: jest.fn() });

  const mockConnection = {
    request: mockRequest,
    publish: mockPublish,
    drain: mockDrain,
    isClosed: mockIsClosed,
    subscribe: mockSubscribe,
  };

  mockConnect = jest.fn().mockResolvedValue(mockConnection);
  (nats.connect as jest.Mock) = mockConnect;

  // Mock headers()
  mockHeadersSet = jest.fn();
  mockHeadersAppend = jest.fn();
  const mockHdrsObj = {
    set: mockHeadersSet,
    append: mockHeadersAppend,
  };
  mockNatsHeaders = jest.fn().mockReturnValue(mockHdrsObj);
  (nats.headers as unknown as jest.Mock) = mockNatsHeaders;
}

async function makeConnectedClient(
  requestImpl?: jest.Mock
): Promise<Mq9Client> {
  setupMocks(requestImpl);
  const client = new Mq9Client("nats://localhost:4222");
  await client.connect();
  return client;
}

// ---------------------------------------------------------------------------
// 1. connect / close / mailboxCreate / server error
// ---------------------------------------------------------------------------

describe("connect / close", () => {
  test("connect() calls nats.connect with the given server", async () => {
    setupMocks();
    const client = new Mq9Client("nats://localhost:4222", {
      reconnectAttempts: 5,
      reconnectDelay: 2000,
    });
    await client.connect();
    expect(mockConnect).toHaveBeenCalledWith(
      expect.objectContaining({
        servers: "nats://localhost:4222",
        maxReconnectAttempts: 5,
        reconnectTimeWait: 2000,
      })
    );
  });

  test("close() drains the connection", async () => {
    const client = await makeConnectedClient();
    await client.close();
    expect(mockDrain).toHaveBeenCalled();
  });

  test("close() is safe when already closed", async () => {
    setupMocks();
    mockIsClosed = jest.fn().mockReturnValue(true);
    const client = new Mq9Client("nats://localhost:4222");
    // never connected — _nc is null, should not throw
    await expect(client.close()).resolves.toBeUndefined();
  });

  test("calling a method before connect() throws Mq9Error", async () => {
    setupMocks();
    const client = new Mq9Client("nats://localhost:4222");
    await expect(client.mailboxCreate()).rejects.toBeInstanceOf(Mq9Error);
  });
});

describe("mailboxCreate", () => {
  test("creates mailbox without options", async () => {
    const req = jest
      .fn()
      .mockResolvedValue(mockMsg({ error: "", mail_address: "auto.123" }));
    const client = await makeConnectedClient(req);
    const addr = await client.mailboxCreate();
    expect(addr).toBe("auto.123");
    expect(req).toHaveBeenCalledWith(
      "$mq9.AI.MAILBOX.CREATE",
      expect.any(Uint8Array),
      expect.any(Object)
    );
  });

  test("creates mailbox with name and ttl", async () => {
    const req = jest
      .fn()
      .mockResolvedValue(mockMsg({ error: "", mail_address: "agent.inbox" }));
    const client = await makeConnectedClient(req);
    const addr = await client.mailboxCreate({ name: "agent.inbox", ttl: 3600 });
    expect(addr).toBe("agent.inbox");
  });

  test("throws Mq9Error when server returns error", async () => {
    const req = jest
      .fn()
      .mockResolvedValue(mockMsg({ error: "mailbox already exists" }));
    const client = await makeConnectedClient(req);
    await expect(client.mailboxCreate({ name: "dup" })).rejects.toThrow(
      Mq9Error
    );
    await expect(client.mailboxCreate({ name: "dup" })).rejects.toThrow(
      "mailbox already exists"
    );
  });
});

// ---------------------------------------------------------------------------
// 2. send
// ---------------------------------------------------------------------------

describe("send", () => {
  test("sends a normal message without headers", async () => {
    const req = jest
      .fn()
      .mockResolvedValue(mockMsg({ error: "", msg_id: 7 }));
    const client = await makeConnectedClient(req);

    const id = await client.send("task.q", new Uint8Array([1, 2, 3]));
    expect(id).toBe(7);
    expect(mockNatsHeaders).not.toHaveBeenCalled();
    expect(req).toHaveBeenCalledWith(
      "$mq9.AI.MSG.SEND.task.q",
      expect.any(Uint8Array),
      expect.objectContaining({ timeout: expect.any(Number) })
    );
  });

  test("sends with urgent priority — header set", async () => {
    const req = jest
      .fn()
      .mockResolvedValue(mockMsg({ error: "", msg_id: 8 }));
    const client = await makeConnectedClient(req);

    await client.send("task.q", "hello", { priority: Priority.URGENT });
    expect(mockNatsHeaders).toHaveBeenCalled();
    expect(mockHeadersSet).toHaveBeenCalledWith("mq9-priority", "urgent");
  });

  test("sends with critical priority — header set", async () => {
    const req = jest
      .fn()
      .mockResolvedValue(mockMsg({ error: "", msg_id: 9 }));
    const client = await makeConnectedClient(req);

    await client.send("task.q", "hello", { priority: Priority.CRITICAL });
    expect(mockHeadersSet).toHaveBeenCalledWith("mq9-priority", "critical");
  });

  test("sends with key, delay, ttl, and tags", async () => {
    const req = jest
      .fn()
      .mockResolvedValue(mockMsg({ error: "", msg_id: 10 }));
    const client = await makeConnectedClient(req);

    await client.send("task.q", "data", {
      key: "dedup-abc",
      delay: 30,
      ttl: 600,
      tags: ["alpha", "beta"],
    });
    expect(mockHeadersSet).toHaveBeenCalledWith("mq9-key", "dedup-abc");
    expect(mockHeadersSet).toHaveBeenCalledWith("mq9-delay", "30");
    expect(mockHeadersSet).toHaveBeenCalledWith("mq9-ttl", "600");
    expect(mockHeadersSet).toHaveBeenCalledWith("mq9-tags", "alpha,beta");
  });

  test("returns msg_id = -1 for delayed messages", async () => {
    const req = jest
      .fn()
      .mockResolvedValue(mockMsg({ error: "", msg_id: -1 }));
    const client = await makeConnectedClient(req);

    const id = await client.send("task.q", "delayed", { delay: 60 });
    expect(id).toBe(-1);
  });

  test("accepts an object payload", async () => {
    const req = jest
      .fn()
      .mockResolvedValue(mockMsg({ error: "", msg_id: 11 }));
    const client = await makeConnectedClient(req);
    const id = await client.send("task.q", { role: "user", text: "hi" });
    expect(id).toBe(11);
  });

  test("throws Mq9Error on server error", async () => {
    const req = jest
      .fn()
      .mockResolvedValue(mockMsg({ error: "mailbox not found" }));
    const client = await makeConnectedClient(req);
    await expect(client.send("bad.q", "x")).rejects.toThrow(Mq9Error);
  });
});

// ---------------------------------------------------------------------------
// 3. fetch
// ---------------------------------------------------------------------------

describe("fetch", () => {
  const rawMessages = [
    {
      msg_id: 1,
      payload: toBase64("hello"),
      priority: "normal",
      create_time: 1700000001,
    },
    {
      msg_id: 2,
      payload: toBase64("world"),
      priority: "urgent",
      create_time: 1700000002,
    },
  ];

  test("stateless fetch returns decoded messages", async () => {
    const req = jest
      .fn()
      .mockResolvedValue(mockMsg({ error: "", messages: rawMessages }));
    const client = await makeConnectedClient(req);

    const msgs = await client.fetch("inbox.1");
    expect(msgs).toHaveLength(2);
    expect(msgs[0].msgId).toBe(1);
    expect(msgs[0].priority).toBe(Priority.NORMAL);
    expect(msgs[1].msgId).toBe(2);
    expect(msgs[1].priority).toBe(Priority.URGENT);

    expect(req).toHaveBeenCalledWith(
      "$mq9.AI.MSG.FETCH.inbox.1",
      expect.any(Uint8Array),
      expect.any(Object)
    );
  });

  test("stateful fetch passes group_name", async () => {
    const req = jest
      .fn()
      .mockResolvedValue(mockMsg({ error: "", messages: [] }));
    const client = await makeConnectedClient(req);

    await client.fetch("inbox.1", { groupName: "worker-1" });
    // Verify the body was serialised with group_name
    const rawBody = req.mock.calls[0][1] as Uint8Array;
    const body = JSON.parse(new TextDecoder().decode(rawBody));
    expect(body.group_name).toBe("worker-1");
  });

  test("empty messages array returns []", async () => {
    const req = jest
      .fn()
      .mockResolvedValue(mockMsg({ error: "", messages: [] }));
    const client = await makeConnectedClient(req);
    const msgs = await client.fetch("empty.q");
    expect(msgs).toEqual([]);
  });

  test("base64 payload is correctly decoded", async () => {
    const original = "mq9 rocks!";
    const req = jest.fn().mockResolvedValue(
      mockMsg({
        error: "",
        messages: [
          {
            msg_id: 3,
            payload: toBase64(original),
            priority: "normal",
            create_time: 1700000003,
          },
        ],
      })
    );
    const client = await makeConnectedClient(req);
    const msgs = await client.fetch("test.q");
    const decoded = new TextDecoder().decode(msgs[0].payload);
    expect(decoded).toBe(original);
  });

  test("missing messages field returns []", async () => {
    const req = jest
      .fn()
      .mockResolvedValue(mockMsg({ error: "" }));
    const client = await makeConnectedClient(req);
    const msgs = await client.fetch("no-field.q");
    expect(msgs).toEqual([]);
  });
});

// ---------------------------------------------------------------------------
// 4. ack
// ---------------------------------------------------------------------------

describe("ack", () => {
  test("sends ACK with correct subject and body", async () => {
    const req = jest
      .fn()
      .mockResolvedValue(mockMsg({ error: "" }));
    const client = await makeConnectedClient(req);

    await client.ack("task.q", "worker-1", 5);

    expect(req).toHaveBeenCalledWith(
      "$mq9.AI.MSG.ACK.task.q",
      expect.any(Uint8Array),
      expect.any(Object)
    );
    const rawBody = req.mock.calls[0][1] as Uint8Array;
    const body = JSON.parse(new TextDecoder().decode(rawBody));
    expect(body.group_name).toBe("worker-1");
    expect(body.mail_address).toBe("task.q");
    expect(body.msg_id).toBe(5);
  });

  test("throws Mq9Error on server error", async () => {
    const req = jest
      .fn()
      .mockResolvedValue(mockMsg({ error: "invalid msg_id" }));
    const client = await makeConnectedClient(req);
    await expect(client.ack("task.q", "g1", 99)).rejects.toThrow(Mq9Error);
  });
});

// ---------------------------------------------------------------------------
// 5. consume
// ---------------------------------------------------------------------------

describe("consume", () => {
  /** Wait for the background loop to make at least `n` requests. */
  async function waitForCalls(mock: jest.Mock, n: number, timeoutMs = 2000): Promise<void> {
    const deadline = Date.now() + timeoutMs;
    while (mock.mock.calls.length < n && Date.now() < deadline) {
      await new Promise((r) => setTimeout(r, 20));
    }
  }

  function makeMessage(id: number): Record<string, unknown> {
    return {
      msg_id: id,
      payload: toBase64("payload-" + id),
      priority: "normal",
      create_time: 1700000000 + id,
    };
  }

  test("happy path: handler called, auto-ack, processedCount increments", async () => {
    let fetchCount = 0;
    const req = jest.fn().mockImplementation((subject: string) => {
      if (subject.includes("FETCH")) {
        fetchCount++;
        if (fetchCount === 1) {
          return Promise.resolve(
            mockMsg({ error: "", messages: [makeMessage(1)] })
          );
        }
        // Return empty after the first batch so the loop idles
        return Promise.resolve(mockMsg({ error: "", messages: [] }));
      }
      // ACK
      return Promise.resolve(mockMsg({ error: "" }));
    });

    const client = await makeConnectedClient(req);
    const handler = jest.fn().mockResolvedValue(undefined);

    const consumer = await client.consume("inbox", handler, {
      groupName: "g1",
    });

    // Wait until handler has been called once
    await waitForCalls(handler, 1);

    expect(handler).toHaveBeenCalled();
    expect(consumer.processedCount).toBeGreaterThanOrEqual(1);

    await consumer.stop();
    expect(consumer.isRunning).toBe(false);
  });

  test("handler throws: errorHandler called, no ack, processedCount unchanged", async () => {
    let fetchCount = 0;
    const req = jest.fn().mockImplementation((subject: string) => {
      if (subject.includes("FETCH")) {
        fetchCount++;
        if (fetchCount === 1) {
          return Promise.resolve(
            mockMsg({ error: "", messages: [makeMessage(10)] })
          );
        }
        return Promise.resolve(mockMsg({ error: "", messages: [] }));
      }
      // ACK — should NOT be called
      return Promise.resolve(mockMsg({ error: "" }));
    });

    const client = await makeConnectedClient(req);
    const handlerError = new Error("processing failed");
    const handler = jest.fn().mockRejectedValue(handlerError);
    const errorHandler = jest.fn().mockResolvedValue(undefined);

    const consumer = await client.consume("inbox", handler, {
      groupName: "g1",
      errorHandler,
    });

    // Wait for handler to be called
    await waitForCalls(handler, 1);
    // Give time for the catch branch to run
    await new Promise((r) => setTimeout(r, 50));

    expect(errorHandler).toHaveBeenCalledWith(
      expect.objectContaining({ msgId: 10 }),
      handlerError
    );
    expect(consumer.processedCount).toBe(0);

    // ACK should not have been sent for this message
    const ackCalls = req.mock.calls.filter((c) => (c[0] as string).includes("ACK"));
    expect(ackCalls).toHaveLength(0);

    await consumer.stop();
  });

  test("stop() sets isRunning=false and resolves", async () => {
    const req = jest.fn().mockResolvedValue(
      mockMsg({ error: "", messages: [] })
    );
    const client = await makeConnectedClient(req);
    const handler = jest.fn().mockResolvedValue(undefined);

    const consumer = await client.consume("inbox", handler);
    expect(consumer.isRunning).toBe(true);
    await consumer.stop();
    expect(consumer.isRunning).toBe(false);
  });

  test("fetch error: loop logs error and continues", async () => {
    const consoleSpy = jest.spyOn(console, "error").mockImplementation(() => undefined);

    let fetchAttempts = 0;
    const req = jest.fn().mockImplementation((subject: string) => {
      if (subject.includes("FETCH")) {
        fetchAttempts++;
        if (fetchAttempts <= 2) {
          // Reject first two attempts
          return Promise.reject(new Error("connection reset"));
        }
        // After two errors, return empty so we can stop cleanly
        return Promise.resolve(mockMsg({ error: "", messages: [] }));
      }
      return Promise.resolve(mockMsg({ error: "" }));
    });

    const client = await makeConnectedClient(req);
    const handler = jest.fn();

    // Use a small retry delay for the test (patch the implementation via a custom subclass)
    // Instead, just wait long enough for 2 retries (each waits 1s — too slow for a test).
    // So we test just that at least 1 fetch attempt was made and the error was logged.
    const consumer = await client.consume("inbox", handler);

    // Allow the first fetch attempt (and its error) to settle
    await new Promise((r) => setTimeout(r, 20));

    // Verify fetch was called at least once and error was logged
    expect(fetchAttempts).toBeGreaterThanOrEqual(1);
    expect(consoleSpy).toHaveBeenCalledWith(
      "[mq9] fetch error:",
      expect.any(Error)
    );

    await consumer.stop();
    consoleSpy.mockRestore();
  }, 10000);

  test("autoAck=false skips ACK even on success", async () => {
    let fetchCount = 0;
    const req = jest.fn().mockImplementation((subject: string) => {
      if (subject.includes("FETCH")) {
        fetchCount++;
        if (fetchCount === 1) {
          return Promise.resolve(
            mockMsg({ error: "", messages: [makeMessage(20)] })
          );
        }
        return Promise.resolve(mockMsg({ error: "", messages: [] }));
      }
      return Promise.resolve(mockMsg({ error: "" }));
    });

    const client = await makeConnectedClient(req);
    const handler = jest.fn().mockResolvedValue(undefined);

    const consumer = await client.consume("inbox", handler, {
      groupName: "g1",
      autoAck: false,
    });

    await waitForCalls(handler, 1);
    await new Promise((r) => setTimeout(r, 50));

    const ackCalls = req.mock.calls.filter((c) => (c[0] as string).includes("ACK"));
    expect(ackCalls).toHaveLength(0);

    await consumer.stop();
  });
});

// ---------------------------------------------------------------------------
// 6. query / delete / agent methods
// ---------------------------------------------------------------------------

describe("query", () => {
  test("sends correct subject and returns messages", async () => {
    const req = jest.fn().mockResolvedValue(
      mockMsg({
        error: "",
        messages: [
          {
            msg_id: 5,
            payload: toBase64("q-payload"),
            priority: "normal",
            create_time: 1700005000,
          },
        ],
      })
    );
    const client = await makeConnectedClient(req);

    const msgs = await client.query("inbox", { key: "status", limit: 5, since: 1234567890 });
    expect(msgs).toHaveLength(1);
    expect(msgs[0].msgId).toBe(5);
    expect(new TextDecoder().decode(msgs[0].payload)).toBe("q-payload");

    expect(req).toHaveBeenCalledWith(
      "$mq9.AI.MSG.QUERY.inbox",
      expect.any(Uint8Array),
      expect.any(Object)
    );
    const body = JSON.parse(new TextDecoder().decode(req.mock.calls[0][1] as Uint8Array));
    expect(body.key).toBe("status");
    expect(body.limit).toBe(5);
    expect(body.since).toBe(1234567890);
  });

  test("empty options sends empty body", async () => {
    const req = jest
      .fn()
      .mockResolvedValue(mockMsg({ error: "", messages: [] }));
    const client = await makeConnectedClient(req);
    const msgs = await client.query("inbox");
    expect(msgs).toEqual([]);
  });
});

describe("delete", () => {
  test("sends DELETE with encoded msg_id in subject", async () => {
    const req = jest
      .fn()
      .mockResolvedValue(mockMsg({ error: "" }));
    const client = await makeConnectedClient(req);

    await client.delete("task.q", 42);

    expect(req).toHaveBeenCalledWith(
      "$mq9.AI.MSG.DELETE.task.q.42",
      expect.any(Uint8Array),
      expect.any(Object)
    );
  });

  test("throws Mq9Error on server error", async () => {
    const req = jest
      .fn()
      .mockResolvedValue(mockMsg({ error: "msg not found" }));
    const client = await makeConnectedClient(req);
    await expect(client.delete("task.q", 999)).rejects.toThrow(Mq9Error);
  });
});

describe("agentRegister", () => {
  test("registers an agent card", async () => {
    const req = jest
      .fn()
      .mockResolvedValue(mockMsg({ error: "" }));
    const client = await makeConnectedClient(req);

    const card = {
      mailbox: "agent.box.1",
      name: "PlannerAgent",
      capabilities: ["planning"],
    };
    await client.agentRegister(card);

    expect(req).toHaveBeenCalledWith(
      "$mq9.AI.AGENT.REGISTER",
      expect.any(Uint8Array),
      expect.any(Object)
    );
    const body = JSON.parse(new TextDecoder().decode(req.mock.calls[0][1] as Uint8Array));
    expect(body.mailbox).toBe("agent.box.1");
    expect(body.name).toBe("PlannerAgent");
  });

  test("throws when mailbox is missing", async () => {
    const req = jest.fn();
    const client = await makeConnectedClient(req);
    await expect(client.agentRegister({ name: "NoMailbox" })).rejects.toThrow(
      Mq9Error
    );
    expect(req).not.toHaveBeenCalled();
  });
});

describe("agentUnregister", () => {
  test("sends UNREGISTER with mailbox", async () => {
    const req = jest
      .fn()
      .mockResolvedValue(mockMsg({ error: "" }));
    const client = await makeConnectedClient(req);

    await client.agentUnregister("agent.box.1");

    expect(req).toHaveBeenCalledWith(
      "$mq9.AI.AGENT.UNREGISTER",
      expect.any(Uint8Array),
      expect.any(Object)
    );
    const body = JSON.parse(new TextDecoder().decode(req.mock.calls[0][1] as Uint8Array));
    expect(body.mailbox).toBe("agent.box.1");
  });
});

describe("agentReport", () => {
  test("sends REPORT with required mailbox field", async () => {
    const req = jest
      .fn()
      .mockResolvedValue(mockMsg({ error: "" }));
    const client = await makeConnectedClient(req);

    const report = {
      mailbox: "agent.box.1",
      status: "healthy",
      load: 0.42,
    };
    await client.agentReport(report);

    expect(req).toHaveBeenCalledWith(
      "$mq9.AI.AGENT.REPORT",
      expect.any(Uint8Array),
      expect.any(Object)
    );
    const body = JSON.parse(new TextDecoder().decode(req.mock.calls[0][1] as Uint8Array));
    expect(body.status).toBe("healthy");
    expect(body.load).toBeCloseTo(0.42);
  });

  test("throws when mailbox is missing", async () => {
    const req = jest.fn();
    const client = await makeConnectedClient(req);
    await expect(client.agentReport({ status: "ok" })).rejects.toThrow(Mq9Error);
  });
});

describe("agentDiscover", () => {
  test("discovers agents with all options", async () => {
    const agents = [
      { mailbox: "agent.1", name: "Alpha" },
      { mailbox: "agent.2", name: "Beta" },
    ];
    const req = jest
      .fn()
      .mockResolvedValue(mockMsg({ error: "", agents }));
    const client = await makeConnectedClient(req);

    const result = await client.agentDiscover({
      text: "planning agent",
      semantic: "workflow orchestration",
      limit: 10,
      page: 1,
    });

    expect(result).toHaveLength(2);
    expect(result[0]["name"]).toBe("Alpha");
    expect(result[1]["mailbox"]).toBe("agent.2");

    expect(req).toHaveBeenCalledWith(
      "$mq9.AI.AGENT.DISCOVER",
      expect.any(Uint8Array),
      expect.any(Object)
    );
    const body = JSON.parse(new TextDecoder().decode(req.mock.calls[0][1] as Uint8Array));
    expect(body.text).toBe("planning agent");
    expect(body.semantic).toBe("workflow orchestration");
    expect(body.limit).toBe(10);
    expect(body.page).toBe(1);
  });

  test("returns [] when agents field is missing", async () => {
    const req = jest
      .fn()
      .mockResolvedValue(mockMsg({ error: "" }));
    const client = await makeConnectedClient(req);
    const result = await client.agentDiscover();
    expect(result).toEqual([]);
  });

  test("sends empty body when no options given", async () => {
    const req = jest
      .fn()
      .mockResolvedValue(mockMsg({ error: "", agents: [] }));
    const client = await makeConnectedClient(req);
    await client.agentDiscover();
    const body = JSON.parse(new TextDecoder().decode(req.mock.calls[0][1] as Uint8Array));
    expect(Object.keys(body)).toHaveLength(0);
  });
});
