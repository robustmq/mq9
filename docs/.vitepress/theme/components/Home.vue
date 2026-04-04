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
      <img src="/flow.svg" alt="mq9 architecture flow" class="flow-img" />

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

.flow-img {
  width: 100%;
  border: 1px solid #e5e5e5;
  border-radius: 8px;
  display: block;
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
