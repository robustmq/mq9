<template>
  <div class="home">

    <!-- Hero + Protocol side by side -->
    <div class="top-row">

      <section class="hero">
        <div class="hero-eyebrow" style="color:#7c3aed">Every Agent deserves a mailbox.</div>
        <h1 class="hero-title">mq9</h1>
        <p class="hero-sub">Agent-to-Agent messaging, solved.</p>
        <p class="hero-desc">
          Running multiple Agents?<br>
          They need to talk to each other.<br>
          mq9 handles it — reliably, asynchronously, at any scale.
        </p>
      </section>

      <section class="protocol">
        <div class="protocol-label">— four subjects, complete API —</div>
        <pre class="protocol-block"><span class="cmd-comment"># create a mailbox</span>
<span class="cmd-subject">$mq9.AI.MAILBOX.CREATE</span>

<span class="cmd-comment"># send to an agent (offline? stored, delivered on reconnect)</span>
<span class="cmd-subject">$mq9.AI.INBOX.<span class="cmd-var">{mail_id}</span>.<span class="cmd-var">{priority}</span></span>

<span class="cmd-comment"># broadcast to all subscribers</span>
<span class="cmd-subject">$mq9.AI.BROADCAST.<span class="cmd-var">{domain}</span>.<span class="cmd-var">{event}</span></span>

<span class="cmd-comment"># pull missed messages after reconnect</span>
<span class="cmd-subject">$mq9.AI.MAILBOX.QUERY.<span class="cmd-var">{mail_id}</span></span></pre>
        <div class="protocol-note">Go, Python, Rust, JavaScript — any NATS client is already an mq9 client.</div>
      </section>

    </div>

    <!-- Diagram -->
    <section class="diagram-section">
      <div class="diagram-label">— how it works —</div>
      <div class="diagram">

        <!-- Left agents -->
        <div class="agent-group">
          <div class="agent">
            <div class="agent-dot online"></div>
            <span>Agent A</span>
          </div>
          <div class="agent">
            <div class="agent-dot online"></div>
            <span>Agent B</span>
          </div>
          <div class="agent">
            <div class="agent-dot offline"></div>
            <span>Agent C</span>
            <span class="agent-note">offline</span>
          </div>
        </div>

        <!-- Arrows left → center -->
        <div class="arrows-left">
          <div class="arrow-row">
            <div class="arrow-line solid"></div>
            <span class="arrow-label green">INBOX.urgent</span>
          </div>
          <div class="arrow-row">
            <div class="arrow-line solid"></div>
            <span class="arrow-label green">INBOX.normal</span>
          </div>
          <div class="arrow-row">
            <div class="arrow-line broadcast"></div>
            <span class="arrow-label purple">BROADCAST</span>
          </div>
        </div>

        <!-- Center: mq9 -->
        <div class="mq9-box">
          <div class="mq9-name">mq9</div>
          <div class="mq9-features">
            <span>store-first</span>
            <span>priority queue</span>
            <span>TTL cleanup</span>
          </div>
        </div>

        <!-- Arrows center → right -->
        <div class="arrows-right">
          <div class="arrow-row">
            <span class="arrow-label green">delivered</span>
            <div class="arrow-line solid right"></div>
          </div>
          <div class="arrow-row">
            <span class="arrow-label green">delivered</span>
            <div class="arrow-line solid right"></div>
          </div>
          <div class="arrow-row">
            <span class="arrow-label green">stored → on reconnect</span>
            <div class="arrow-line dashed right"></div>
          </div>
        </div>

        <!-- Right agents -->
        <div class="agent-group">
          <div class="agent right">
            <div class="agent-dot online"></div>
            <span>Agent D</span>
          </div>
          <div class="agent right">
            <div class="agent-dot online"></div>
            <span>Agent E</span>
          </div>
          <div class="agent right">
            <div class="agent-dot offline"></div>
            <span>Agent F</span>
            <span class="agent-note">reconnects later</span>
          </div>
        </div>

      </div>

      <!-- Capabilities row -->
      <div class="caps-row">
        <div class="cap-item">
          <span class="cap-icon" style="color:#16a34a">⊙</span>
          <span class="cap-title">Point-to-point</span>
          <span class="cap-desc">Deliver to a specific agent mailbox. Recipient offline? Message waits.</span>
        </div>
        <div class="cap-divider"></div>
        <div class="cap-item">
          <span class="cap-icon" style="color:#7c3aed">⊕</span>
          <span class="cap-title">Broadcast</span>
          <span class="cap-desc">Publish once. All subscribers receive. Advertise capabilities to the network.</span>
        </div>
        <div class="cap-divider"></div>
        <div class="cap-item">
          <span class="cap-icon" style="color:#16a34a">⊗</span>
          <span class="cap-title">Offline recovery</span>
          <span class="cap-desc">Agent comes back online. Pulls missed messages. Nothing lost.</span>
        </div>
        <div class="cap-divider"></div>
        <div class="cap-item">
          <span class="cap-icon" style="color:#7c3aed">○</span>
          <span class="cap-title">Single binary</span>
          <span class="cap-desc">One Docker command. Runs standalone. Scales to thousands of agents.</span>
        </div>
      </div>
    </section>

    <!-- Divider -->
    <div class="section-divider"></div>

    <!-- Audiences -->
    <section class="audiences">
      <a href="/for-agent" class="audience-row">
        <div class="audience-meta">
          <span class="audience-num">01</span>
          <span class="audience-tag">Agent</span>
        </div>
        <div class="audience-body">
          <div class="audience-title">For Agent</div>
          <div class="audience-desc">You go offline. Tasks keep coming. Messages sent while you were gone should not disappear. mq9 gives you a mailbox — request one per task, subscribe when ready, get everything that arrived. Nothing lost, no retry logic needed.</div>
        </div>
        <div class="audience-arrow">→</div>
      </a>

      <a href="/for-engineer" class="audience-row">
        <div class="audience-meta">
          <span class="audience-num">02</span>
          <span class="audience-tag">Engineer</span>
        </div>
        <div class="audience-body">
          <div class="audience-title">For Engineer</div>
          <div class="audience-desc">Agents going offline breaks delivery. Polling databases doesn't scale. Building your own queue takes weeks. mq9 runs as a single binary — one Docker command, any NATS client, zero new SDK. Persistent delivery, broadcast, and offline recovery out of the box.</div>
        </div>
        <div class="audience-arrow">→</div>
      </a>
    </section>

  </div>
</template>

<style scoped>
* { box-sizing: border-box; }

.home {
  min-height: 100vh;
  background: #fff;
  color: #000;
  font-family: ui-monospace, 'JetBrains Mono', 'Fira Code', monospace;
  max-width: 1200px;
  margin: 0 auto;
  padding: 0 4rem;
  display: flex;
  flex-direction: column;
}

/* ─── Top row ────────────────────────────────────────────────── */
.top-row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8rem;
  align-items: center;
  padding: 4rem 0 6rem;
}

/* ─── Hero ───────────────────────────────────────────────────── */
.hero {
  display: flex;
  flex-direction: column;
  gap: 1.5rem;
  align-items: center;
  text-align: center;
}

.hero-eyebrow {
  font-size: 0.72rem;
  color: #999;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.hero-title {
  font-size: 7rem;
  font-weight: 700;
  letter-spacing: -0.04em;
  line-height: 1;
  margin: 0;
  color: #000;
  font-family: 'Space Grotesk', sans-serif;
}

.hero-sub {
  font-size: 1.1rem;
  font-weight: 500;
  color: #000;
  margin: 0;
  letter-spacing: -0.01em;
}

.hero-desc {
  font-size: 0.85rem;
  line-height: 2;
  color: #666;
  margin: 0;
}

/* ─── Protocol ───────────────────────────────────────────────── */
.protocol {
  display: flex;
  flex-direction: column;
  gap: 1.5rem;
}

.protocol-label {
  font-size: 0.7rem;
  color: #bbb;
  letter-spacing: 0.1em;
  text-transform: uppercase;
}

.protocol-block {
  background: #000;
  color: #e5e5e5;
  border-radius: 4px;
  padding: 2rem 2.5rem;
  font-family: ui-monospace, 'JetBrains Mono', monospace;
  font-size: 0.82rem;
  line-height: 2.2;
  margin: 0;
  overflow-x: auto;
  border: none;
  white-space: pre;
}

.cmd-comment { color: #555; }
.cmd-subject { color: #fff; font-weight: 600; }
.cmd-var     { color: #aaa; font-weight: 400; }

.protocol-note {
  font-size: 0.75rem;
  color: #999;
  line-height: 1.7;
}

/* ─── Diagram ────────────────────────────────────────────────── */
.diagram-section {
  padding: 0 0 5rem;
  display: flex;
  flex-direction: column;
  gap: 3rem;
}

.diagram-label {
  font-size: 0.7rem;
  color: #bbb;
  letter-spacing: 0.1em;
  text-transform: uppercase;
}

.diagram {
  display: flex;
  align-items: center;
  gap: 0;
  border: 1px solid #e5e5e5;
  border-radius: 8px;
  padding: 3rem 2.5rem;
  background: #fafafa;
}

/* Agent groups */
.agent-group {
  display: flex;
  flex-direction: column;
  gap: 1.6rem;
  flex-shrink: 0;
}

.agent {
  display: flex;
  align-items: center;
  gap: 0.6rem;
  font-size: 0.78rem;
  font-weight: 600;
  color: #111;
  position: relative;
}

.agent.right {
  flex-direction: row-reverse;
}

.agent-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
}
.agent-dot.online  { background: #16a34a; }
.agent-dot.offline { background: #ccc; }

.agent-note {
  font-size: 0.62rem;
  color: #bbb;
  font-weight: 400;
  margin-left: 0.2rem;
}

/* Arrow columns */
.arrows-left,
.arrows-right {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 1.6rem;
  padding: 0 1rem;
}

.arrow-row {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.arrow-line {
  flex: 1;
  height: 1px;
  position: relative;
}

.arrow-line.solid {
  background: #16a34a;
}

.arrow-line.broadcast {
  background: repeating-linear-gradient(90deg, #7c3aed 0, #7c3aed 5px, transparent 5px, transparent 10px);
}

.arrow-line.dashed {
  background: repeating-linear-gradient(90deg, #16a34a 0, #16a34a 5px, transparent 5px, transparent 10px);
}

/* arrowhead pointing right */
.arrow-line:not(.right)::after {
  content: '';
  position: absolute;
  right: -1px;
  top: -3px;
  border: 4px solid transparent;
  border-left-color: #16a34a;
}
.arrow-line.broadcast::after {
  border-left-color: #7c3aed;
}
.arrow-line.dashed::after {
  border-left-color: #16a34a;
}
/* arrowhead pointing right on right side */
.arrow-line.right::after {
  content: '';
  position: absolute;
  right: -1px;
  top: -3px;
  border: 4px solid transparent;
  border-left-color: #16a34a;
}
.arrow-line.dashed.right::after {
  border-left-color: #16a34a;
}

.arrows-right .arrow-row {
  flex-direction: row-reverse;
}
.arrows-right .arrow-line:not(.right)::after {
  display: none;
}
.arrows-right .arrow-line::before {
  content: '';
  position: absolute;
  right: -1px;
  top: -3px;
  border: 4px solid transparent;
  border-left-color: #16a34a;
}
.arrows-right .arrow-line.dashed::before {
  border-left-color: #16a34a;
}

.arrow-label {
  font-size: 0.62rem;
  color: #999;
  white-space: nowrap;
  letter-spacing: 0.02em;
}
.arrow-label.green  { color: #16a34a; }
.arrow-label.purple { color: #7c3aed; }

/* mq9 center box */
.mq9-box {
  flex-shrink: 0;
  width: 120px;
  border: 1.5px solid #000;
  border-left: 3px solid #7c3aed;
  border-radius: 6px;
  padding: 1.2rem 1rem;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.8rem;
  background: #fff;
}

.mq9-name {
  font-size: 1.1rem;
  font-weight: 700;
  letter-spacing: -0.02em;
  color: #000;
}

.mq9-features {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.25rem;
}

.mq9-features span {
  font-size: 0.58rem;
  color: #999;
  letter-spacing: 0.04em;
  text-transform: uppercase;
}

/* Capabilities row */
.caps-row {
  display: flex;
  align-items: stretch;
  border: 1px solid #e5e5e5;
  border-radius: 8px;
  overflow: hidden;
}

.cap-item {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 0.6rem;
  padding: 1.8rem 1.6rem;
}

.cap-divider {
  width: 1px;
  background: #e5e5e5;
  flex-shrink: 0;
}

.cap-icon {
  font-size: 1rem;
  color: #000;
  font-style: normal;
}

.cap-title {
  font-size: 0.82rem;
  font-weight: 700;
  color: #000;
  letter-spacing: -0.01em;
}

.cap-desc {
  font-size: 0.75rem;
  color: #888;
  line-height: 1.7;
}

/* ─── Divider ────────────────────────────────────────────────── */
.section-divider {
  height: 1px;
  background: #e5e5e5;
}

/* ─── Audiences ──────────────────────────────────────────────── */
.audiences {
  display: flex;
  flex-direction: column;
}

.audience-row {
  display: grid;
  grid-template-columns: 6rem 1fr 2rem;
  gap: 2rem;
  align-items: start;
  padding: 3rem 0;
  border-bottom: 1px solid #e5e5e5;
  text-decoration: none;
  color: inherit;
}

.audience-meta {
  display: flex;
  flex-direction: column;
  gap: 0.4rem;
  padding-top: 0.1rem;
}

.audience-num {
  font-size: 0.65rem;
  color: #ccc;
  letter-spacing: 0.05em;
}

.audience-tag {
  font-size: 0.65rem;
  color: #999;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  border: 1px solid #e5e5e5;
  padding: 0.15rem 0.4rem;
  border-radius: 2px;
  width: fit-content;
}

.audience-body {
  display: flex;
  flex-direction: column;
  gap: 0.8rem;
}

.audience-title {
  font-size: 1rem;
  font-weight: 700;
  color: #000;
  letter-spacing: -0.01em;
}

.audience-desc {
  font-size: 0.8rem;
  line-height: 1.9;
  color: #666;
}

.audience-arrow {
  font-size: 1rem;
  color: #ccc;
  padding-top: 0.1rem;
  transition: transform 0.15s, color 0.15s;
}

.audience-row:hover .audience-arrow {
  color: #000;
  transform: translateX(4px);
}

/* ─── Footer ─────────────────────────────────────────────────── */
.site-footer {
  display: flex;
  justify-content: space-between;
  padding: 2.5rem 0;
  margin-top: auto;
  font-size: 0.72rem;
  color: #bbb;
  border-top: 1px solid #e5e5e5;
}

.site-footer a {
  color: #bbb;
  text-decoration: none;
}
.site-footer a:hover { color: #000; }

/* ─── Responsive ─────────────────────────────────────────────── */
@media (max-width: 900px) {
  .diagram { flex-wrap: wrap; gap: 1.5rem; justify-content: center; }
  .arrows-left, .arrows-right { display: none; }
  .caps-row { flex-direction: column; }
  .cap-divider { width: auto; height: 1px; }
}

@media (max-width: 768px) {
  .top-row { grid-template-columns: 1fr; gap: 3rem; padding: 5rem 0 4rem; }
}

@media (max-width: 640px) {
  .home { padding: 0 1.25rem; }
  .hero-title { font-size: 4.5rem; }
  .audience-row { grid-template-columns: 4rem 1fr 1.5rem; gap: 1rem; }
  .protocol-block { padding: 1.5rem; font-size: 0.75rem; }
}
</style>
