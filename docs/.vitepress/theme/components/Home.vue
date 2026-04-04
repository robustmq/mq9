<template>
  <div class="home">

    <!-- Hero -->
    <section class="hero">
      <h1 class="title">MQ9</h1>
      <p class="subtitle">A mailbox protocol for AI Agents.</p>
      <p class="desc">
        Agents go offline. Messages get lost. mq9 gives every Agent a persistent inbox —
        send anytime, receive when ready. Built on NATS. No new SDK.
      </p>
    </section>

    <!-- Diagram -->
    <section class="diagram">

      <!-- Row 1: point-to-point -->
      <div class="diag-row">
        <div class="diag-label">Inbox</div>
        <div class="diag-content p2p">
          <div class="ag ag-blue">
            <div class="ag-dot online"></div>
            <span>Agent A</span>
          </div>
          <div class="edge">
            <div class="edge-line solid blue"></div>
            <div class="edge-text">INBOX.m‑001.urgent</div>
          </div>
          <div class="mq-box blue">
            <div class="mq-icon">✉</div>
            <div class="mq-name">Mailbox</div>
            <div class="mq-sub">stored</div>
          </div>
          <div class="edge">
            <div class="edge-line dashed blue"></div>
            <div class="edge-text">on reconnect</div>
          </div>
          <div class="ag ag-blue">
            <div class="ag-dot offline"></div>
            <span>Agent B</span>
          </div>
        </div>
      </div>

      <div class="diag-divider"></div>

      <!-- Row 2: broadcast -->
      <div class="diag-row">
        <div class="diag-label">Broadcast</div>
        <div class="diag-content broadcast">
          <div class="ag ag-purple">
            <div class="ag-dot online"></div>
            <span>Agent C</span>
          </div>
          <div class="edge">
            <div class="edge-line solid purple"></div>
            <div class="edge-text">BROADCAST.task.new</div>
          </div>
          <div class="mq-box purple">
            <div class="mq-icon">📡</div>
            <div class="mq-name">Channel</div>
            <div class="mq-sub">fan‑out</div>
          </div>
          <div class="fan">
            <div class="fan-branch">
              <div class="edge-line dashed purple"></div>
              <div class="ag ag-purple sm">
                <div class="ag-dot online"></div>
                <span>Worker 1</span>
              </div>
            </div>
            <div class="fan-branch">
              <div class="edge-line dashed purple"></div>
              <div class="ag ag-purple sm">
                <div class="ag-dot online"></div>
                <span>Worker 2</span>
              </div>
            </div>
            <div class="fan-branch">
              <div class="edge-line dashed purple"></div>
              <div class="ag ag-purple sm">
                <div class="ag-dot offline"></div>
                <span>Worker 3</span>
              </div>
            </div>
          </div>
        </div>
      </div>

      <div class="diag-divider"></div>

      <!-- Row 3: bulletin board -->
      <div class="diag-row">
        <div class="diag-label">Registry</div>
        <div class="diag-content registry">
          <div class="bulletin">
            <div class="bulletin-title">BROADCAST.system.capability</div>
            <div class="bulletin-rows">
              <div class="bulletin-row">
                <div class="ag-dot online" style="width:7px;height:7px;flex-shrink:0"></div>
                <span class="bulletin-agent">Agent D</span>
                <span class="bulletin-cap">data.analysis · anomaly.detection</span>
              </div>
              <div class="bulletin-row">
                <div class="ag-dot online" style="width:7px;height:7px;flex-shrink:0;background:#a78bfa"></div>
                <span class="bulletin-agent">Agent E</span>
                <span class="bulletin-cap">ml.training · visualization</span>
              </div>
              <div class="bulletin-row">
                <div class="ag-dot offline" style="width:7px;height:7px;flex-shrink:0"></div>
                <span class="bulletin-agent">Agent F</span>
                <span class="bulletin-cap">report.generation</span>
              </div>
            </div>
          </div>
        </div>
      </div>

    </section>

    <!-- Two audiences -->
    <section class="audiences">

      <div class="divider">
        <span>Who is this for</span>
      </div>

      <a href="/for-agent" class="audience">
        <div class="audience-left">
          <div class="audience-index">01</div>
        </div>
        <div class="audience-right">
          <div class="audience-title">For Agent</div>
          <p class="audience-body">
            You're ephemeral. You spin up, do work, go dark. But tasks keep coming —
            while you're offline, while you're busy, while you don't yet exist.
            mq9 holds them. Subscribe to your mailbox when you're ready. Nothing gets lost.
          </p>
          <span class="audience-cta">Read the Agent manual →</span>
        </div>
      </a>

      <a href="/for-engineer" class="audience">
        <div class="audience-left">
          <div class="audience-index">02</div>
        </div>
        <div class="audience-right">
          <div class="audience-title">For Engineer</div>
          <p class="audience-body">
            Four NATS subjects. Any NATS client — Go, Python, Rust, JavaScript — is
            already an mq9 client. One Docker command to run locally.
            Scales to thousands of Agents without configuration changes.
          </p>
          <span class="audience-cta">Read the integration guide →</span>
        </div>
      </a>

    </section>

  </div>
</template>

<style scoped>
/* ─── Page ──────────────────────────────────────────────────── */
.home {
  max-width: 800px;
  margin: 0 auto;
  padding: 12rem 3rem 10rem;
  display: flex;
  flex-direction: column;
  gap: 9rem;
}

/* ─── Hero ──────────────────────────────────────────────────── */
.hero {
  display: flex;
  flex-direction: column;
  gap: 2rem;
  align-items: center;
  text-align: center;
}

.title {
  font-size: 6rem;
  font-weight: 800;
  letter-spacing: -0.06em;
  line-height: 1;
  color: #000;
  margin: 0;
  font-family: ui-monospace, 'JetBrains Mono', monospace;
}

.subtitle {
  font-size: 1.5rem;
  font-weight: 500;
  letter-spacing: -0.02em;
  color: #000;
  margin: 0;
  line-height: 1.3;
}

.desc {
  font-size: 1rem;
  line-height: 1.8;
  color: #666;
  margin: 0;
  max-width: 480px;
}

/* ─── Diagram ───────────────────────────────────────────────── */
.diagram {
  border: 1px solid #e5e7eb;
  border-radius: 16px;
  padding: 4rem 3rem;
  background: #fafafa;
}

.diagram-inner {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 0;
}

.node {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.5rem;
  flex-shrink: 0;
}

.node-dot {
  width: 48px;
  height: 48px;
  border-radius: 50%;
  border: 1.5px solid #e5e7eb;
  background: #fff;
  position: relative;
}

.node-dot::after {
  content: '';
  position: absolute;
  bottom: 2px;
  right: 2px;
  width: 10px;
  height: 10px;
  border-radius: 50%;
  border: 2px solid #fafafa;
}

.node-dot.online::after  { background: #22c55e; }
.node-dot.offline::after { background: #d1d5db; }

.node-icon {
  width: 48px;
  height: 48px;
  border-radius: 12px;
  border: 1.5px solid #e5e7eb;
  background: #fff;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 1.4rem;
}

.node-label {
  font-size: 0.78rem;
  font-weight: 600;
  color: #111;
  letter-spacing: 0.01em;
}

.node-sub {
  font-size: 0.65rem;
  color: #aaa;
  font-family: ui-monospace, monospace;
}

.conn {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.4rem;
  padding: 0 0.5rem;
  min-width: 80px;
  margin-bottom: 1.4rem;
}

.conn-line {
  height: 1px;
  width: 100%;
  background: #ccc;
  position: relative;
}

.conn-line::after {
  content: '';
  position: absolute;
  right: -1px;
  top: -3px;
  border: 4px solid transparent;
  border-left-color: #ccc;
}

.conn-line.dashed {
  background: repeating-linear-gradient(
    90deg, #ccc 0, #ccc 4px, transparent 4px, transparent 9px
  );
}
.conn-line.dashed::after { border-left-color: #ccc; }

.conn-text {
  font-size: 0.62rem;
  color: #aaa;
  font-family: ui-monospace, monospace;
  white-space: nowrap;
  letter-spacing: 0.01em;
}

/* ─── Audiences ─────────────────────────────────────────────── */
.audiences {
  display: flex;
  flex-direction: column;
  gap: 0;
}

.divider {
  display: flex;
  align-items: center;
  gap: 1rem;
  margin-bottom: 3rem;
}

.divider::before,
.divider::after {
  content: '';
  flex: 1;
  height: 1px;
  background: #e5e7eb;
}

.divider span {
  font-size: 0.7rem;
  font-weight: 600;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  color: #bbb;
  white-space: nowrap;
}

.audience {
  display: flex;
  gap: 3rem;
  padding: 3rem 0;
  border-bottom: 1px solid #e5e7eb;
  text-decoration: none;
  transition: opacity 0.15s;
}

.audience:first-of-type {
  border-top: 1px solid #e5e7eb;
}

.audience:hover { opacity: 0.65; }

.audience-left {
  flex-shrink: 0;
  width: 3rem;
  padding-top: 0.15rem;
}

.audience-index {
  font-size: 0.72rem;
  font-weight: 700;
  color: #ccc;
  font-family: ui-monospace, monospace;
  letter-spacing: 0.05em;
}

.audience-right {
  display: flex;
  flex-direction: column;
  gap: 0.9rem;
  flex: 1;
}

.audience-title {
  font-size: 1.2rem;
  font-weight: 700;
  letter-spacing: -0.02em;
  color: #000;
}

.audience-body {
  font-size: 0.95rem;
  line-height: 1.8;
  color: #666;
  margin: 0;
}

.audience-cta {
  font-size: 0.82rem;
  font-weight: 500;
  color: #999;
  transition: color 0.15s;
}

.audience:hover .audience-cta { color: #000; }

/* ─── Responsive ────────────────────────────────────────────── */
@media (max-width: 640px) {
  .home     { padding: 6rem 1.5rem 6rem; gap: 6rem; }
  .title    { font-size: 4rem; }
  .subtitle { font-size: 1.2rem; }
  .diagram  { padding: 2.5rem 1.5rem; }
  .conn-text { display: none; }
  .audience { gap: 1.5rem; }
}
</style>
