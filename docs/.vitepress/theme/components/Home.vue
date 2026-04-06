<template>
  <div class="home">

    <!-- 1. Hero: what is mq9 -->
    <section class="hero">
      <h1 class="hero-title">mq9</h1>
      <p class="hero-sub">A message broker for AI Agents.</p>
      <p class="hero-def">
        Deploy once. Every Agent gets a mailbox.<br>
        Send to any Agent — online or offline. Messages are stored and delivered when ready.<br>
        Point-to-point, broadcast, offline recovery. One binary, nothing else to install.
      </p>
    </section>

    <!-- 2. Why not HTTP / Kafka -->
    <section class="compare-section">
      <div class="section-label">— why not HTTP or Kafka —</div>
      <div class="compare-row">
        <div class="compare-item">
          <div class="compare-name">HTTP</div>
          <div class="compare-problem">Both sides must be online. Agent goes offline — message lost. No retry, no persistence built in.</div>
        </div>
        <div class="compare-divider"></div>
        <div class="compare-item">
          <div class="compare-name">Kafka</div>
          <div class="compare-problem">Built for high-throughput data pipelines, not ephemeral agents. Topics, partitions, consumer groups — too heavy for agent messaging.</div>
        </div>
        <div class="compare-divider"></div>
        <div class="compare-item">
          <div class="compare-name">Redis pub/sub</div>
          <div class="compare-problem">Fire-and-forget. No persistence. Agent offline when message arrives — message gone. Adding Redis Streams brings consumer group complexity.</div>
        </div>
        <div class="compare-divider"></div>
        <div class="compare-item highlight">
          <div class="compare-name mq9-name-inline">mq9</div>
          <div class="compare-problem">Built for agents. Store-first delivery. Offline agent? Message waits. Reconnects — gets everything. No retry logic, no polling, no coordination overhead.</div>
        </div>
      </div>
    </section>

    <!-- 3. Diagram -->
    <section class="diagram-section">
      <div class="section-label">— how it works —</div>
      <img src="/flow.svg" alt="mq9 architecture flow" class="flow-img" />
    </section>

    <!-- 4. Protocol -->
    <section class="protocol-section">
      <div class="section-label">— three subjects, complete API —</div>
      <div class="protocol-wrap">
        <pre class="protocol-block"><span class="cmd-comment"># create a mailbox</span>
<span class="cmd-subject">$mq9.AI.MAILBOX.CREATE</span>

<span class="cmd-comment"># send to a mailbox (offline? stored, delivered on reconnect)</span>
<span class="cmd-subject">$mq9.AI.MAILBOX.<span class="cmd-var">{mail_id}</span>.<span class="cmd-var">{priority}</span></span>

<span class="cmd-comment"># subscribe — all unexpired messages pushed immediately</span>
<span class="cmd-subject">$mq9.AI.MAILBOX.<span class="cmd-var">{mail_id}</span>.*</span>

<span class="cmd-comment"># discover all public mailboxes</span>
<span class="cmd-subject">$mq9.AI.PUBLIC.LIST</span></pre>
        <div class="protocol-note">Works with any NATS client — Go, Python, Rust, JavaScript. No new SDK required.</div>
      </div>
    </section>

    <!-- 5. Features -->
    <section class="caps-section">
      <div class="caps-row">
        <div class="cap-item">
          <span class="cap-icon" style="color:#16a34a">⊙</span>
          <span class="cap-title">Point-to-point</span>
          <span class="cap-desc">Deliver to a specific agent mailbox. Recipient offline? Message waits, delivered on reconnect.</span>
        </div>
        <div class="cap-divider"></div>
        <div class="cap-item">
          <span class="cap-icon" style="color:#7c3aed">⊕</span>
          <span class="cap-title">Public mailboxes</span>
          <span class="cap-desc">Create a named public mailbox. Any Agent can discover it via PUBLIC.LIST and subscribe. No registry to maintain.</span>
        </div>
        <div class="cap-divider"></div>
        <div class="cap-item">
          <span class="cap-icon" style="color:#16a34a">⊗</span>
          <span class="cap-title">Offline recovery</span>
          <span class="cap-desc">Agent reconnects and gets everything it missed. Nothing lost, no retry logic needed.</span>
        </div>
        <div class="cap-divider"></div>
        <div class="cap-item">
          <span class="cap-icon" style="color:#7c3aed">○</span>
          <span class="cap-title">Single binary</span>
          <span class="cap-desc">One Docker command. No dependencies. Scales to thousands of agents without config changes.</span>
        </div>
      </div>
    </section>

    <!-- Divider -->
    <div class="section-divider"></div>

    <!-- 6. Audiences -->
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

    <!-- Footer -->
    <footer class="home-footer">
      <span class="slogan">Every Agent deserves a mailbox.</span>
      <div class="footer-meta">
        <span>Built on <a href="https://github.com/robustmq/robustmq" target="_blank">RobustMQ</a></span>
        <span>© 2025 mq9</span>
      </div>
    </footer>

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
  gap: 4rem;
}

/* ─── Hero ───────────────────────────────────────────────────── */
.hero {
  display: flex;
  flex-direction: column;
  gap: 1.5rem;
  padding: 4rem 0 0;
  align-items: center;
  text-align: center;
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
  font-size: 1.4rem;
  font-weight: 600;
  color: #000;
  margin: 0;
  letter-spacing: -0.02em;
}

.hero-def {
  font-size: 0.9rem;
  line-height: 2;
  color: #555;
  margin: 0;
}

/* ─── Section label ──────────────────────────────────────────── */
.section-label {
  font-size: 0.7rem;
  color: #bbb;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  margin-bottom: 1.5rem;
}

/* ─── Compare ────────────────────────────────────────────────── */
.compare-section { display: flex; flex-direction: column; }

.compare-row {
  display: flex;
  align-items: stretch;
  border: 1px solid #e5e5e5;
  border-radius: 8px;
  overflow: hidden;
}

.compare-item {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 0.6rem;
  padding: 1.8rem 1.6rem;
}

.compare-item.highlight {
  background: #fafafa;
}

.compare-divider {
  width: 1px;
  background: #e5e5e5;
  flex-shrink: 0;
}

.compare-name {
  font-size: 0.82rem;
  font-weight: 700;
  color: #bbb;
  letter-spacing: 0.02em;
}

.mq9-name-inline {
  color: #000 !important;
}

.compare-problem {
  font-size: 0.75rem;
  color: #888;
  line-height: 1.7;
}

.compare-item.highlight .compare-problem {
  color: #444;
}

/* ─── Diagram ────────────────────────────────────────────────── */
.diagram-section { display: flex; flex-direction: column; }

.flow-img {
  width: 100%;
  border: 1px solid #e5e5e5;
  border-radius: 8px;
  display: block;
}

/* ─── Protocol ───────────────────────────────────────────────── */
.protocol-section {
  display: flex;
  flex-direction: column;
  align-items: center;
  text-align: center;
}

.protocol-wrap {
  display: flex;
  flex-direction: column;
  gap: 1.2rem;
  max-width: 640px;
  width: 100%;
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

/* ─── Features ───────────────────────────────────────────────── */
.caps-section { display: flex; flex-direction: column; }

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

.cap-icon { font-size: 1rem; }

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
  margin: 0;
}

/* ─── Audiences ──────────────────────────────────────────────── */
.audiences {
  display: flex;
  flex-direction: column;
  gap: 0;
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

/* ─── Slogan ─────────────────────────────────────────────────── */
.home-footer {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.6rem;
  padding: 1.2rem 0 1rem;
  border-top: 1px solid #e5e5e5;
  margin-top: 0;
}

.slogan {
  font-size: 1.3rem;
  font-weight: 700;
  color: #7c3aed;
  letter-spacing: -0.01em;
}

.footer-meta {
  display: flex;
  gap: 2rem;
  font-size: 0.72rem;
  color: #bbb;
}

.footer-meta a {
  color: #bbb;
  text-decoration: none;
}
.footer-meta a:hover { color: #000; }

/* ─── Responsive ─────────────────────────────────────────────── */
@media (max-width: 900px) {
  .compare-row { flex-direction: column; }
  .compare-divider { width: auto; height: 1px; }
  .caps-row { flex-direction: column; }
  .cap-divider { width: auto; height: 1px; }
}

@media (max-width: 768px) {
  .home { padding: 0 2rem; gap: 4rem; }
  .hero-title { font-size: 5rem; }
}

@media (max-width: 640px) {
  .home { padding: 0 1.25rem; }
  .hero-title { font-size: 4rem; }
  .audience-row { grid-template-columns: 4rem 1fr 1.5rem; gap: 1rem; }
  .protocol-block { padding: 1.5rem; font-size: 0.75rem; }
}
</style>
