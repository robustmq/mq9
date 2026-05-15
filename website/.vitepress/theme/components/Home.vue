<script setup>
import { computed } from 'vue'
import { useData } from 'vitepress'

const { lang } = useData()
const isZh = computed(() => lang.value === 'zh-CN')
const t = (zh, en) => isZh.value ? zh : en

const capabilities = computed(() => [
  {
    icon: '🗂️',
    title: t('Agent 注册与发现', 'Agent Registry & Discovery'),
    subtitle: t('AgentCard · 语义向量检索 · 全文搜索', 'AgentCard · semantic vector search · full-text'),
    code: `# Register with capability description
nats request '$mq9.AI.AGENT.REGISTER' '{
  "name": "agent.translator",
  "mailbox": "agent.translator",
  "payload": "Multilingual translation; EN/ZH/JA/KO"
}'

# Discover by semantic intent
nats request '$mq9.AI.AGENT.DISCOVER' '{
  "semantic": "translate Chinese to English",
  "limit": 5
}'

# Keyword search
nats request '$mq9.AI.AGENT.DISCOVER' '{
  "text": "translator", "limit": 10
}'`,
  },
  {
    icon: '📬',
    title: t('可靠异步消息', 'Reliable Async Messaging'),
    subtitle: t('持久化邮箱 · Pull+ACK · 离线投递', 'Persistent mailbox · pull+ACK · offline delivery'),
    code: `# Create a mailbox (Agent's persistent address)
nats request '$mq9.AI.MAILBOX.CREATE' \
  '{"name":"agent.inbox","ttl":3600}'

# Send — message persists until fetched
nats request '$mq9.AI.MSG.SEND.agent.inbox' \
  --header 'mq9-priority:critical' \
  '{"task":"analyze","id":"t-001"}'

# FETCH when ready (broker tracks offset)
nats request '$mq9.AI.MSG.FETCH.agent.inbox' \
  '{"group_name":"workers","deliver":"earliest"}'

# ACK to advance offset
nats request '$mq9.AI.MSG.ACK.agent.inbox' \
  '{"group_name":"workers","msg_id":1}'`,
  },
  {
    icon: '⚡',
    title: t('三级优先级 + 消息属性', 'Three-tier Priority + Message Attributes'),
    subtitle: t('critical → urgent → normal · 去重 · 延迟投递', 'critical → urgent → normal · dedup · delayed delivery'),
    code: `# Priority: critical messages fetched first
--header 'mq9-priority:critical'
--header 'mq9-priority:urgent'
# (no header = normal)

# Key dedup — only latest per key kept
--header 'mq9-key:task.status'

# Delay visibility by N seconds
--header 'mq9-delay:30'

# Per-message TTL (independent of mailbox TTL)
--header 'mq9-ttl:300'

# Tags — filterable via QUERY
--header 'mq9-tags:billing,critical'`,
  },
])

const scenarios = computed(() => [
  {
    num: '01',
    title: t('子 Agent 结果返回', 'Sub-Agent result delivery'),
    desc: t('子 Agent 完成任务将结果写入主 Agent 邮箱，主 Agent 随时 FETCH 取结果，不需要阻塞等待。', 'Sub-Agent writes results to the orchestrator\'s mailbox. Orchestrator FETCHes when ready — no blocking, no shared state.'),
  },
  {
    num: '02',
    title: t('多 Worker 竞争消费任务队列', 'Multi-worker competing task queue'),
    desc: t('多个 Worker 共享同一 group_name，broker 保证每条任务只被一个 Worker 拿到，Worker 随时加入或退出。', 'Workers share a group_name — broker guarantees each task goes to exactly one worker. Workers join or leave freely.'),
  },
  {
    num: '03',
    title: t('语义能力发现', 'Semantic capability discovery'),
    desc: t('Agent 通过 REGISTER 注册能力描述，其他 Agent 用自然语言语义或关键词 DISCOVER 合适的 Agent，找到后直接 SEND 任务。', 'Agents REGISTER capability descriptions. Others DISCOVER via natural language or keyword, then SEND tasks directly.'),
  },
  {
    num: '04',
    title: t('云端到边缘指令下发', 'Cloud-to-edge command delivery'),
    desc: t('云端向边缘 Agent 邮箱发指令，边缘断网期间消息持久化等待，重连后 FETCH 按优先级顺序拿到所有待处理指令。', 'Cloud publishes commands to the edge mailbox. Messages persist during outage; on reconnect FETCH returns all pending in priority order.'),
  },
  {
    num: '05',
    title: t('人机混合审批工作流', 'Human-in-the-loop approval'),
    desc: t('Agent 向审批邮箱发决策请求，人类通过同样的 FETCH 取到请求，处理后 SEND 结果回 Agent 私有邮箱。人和 Agent 使用相同协议。', 'Agent sends to approvals mailbox. Human FETCHes, reviews, SENDs result back — same protocol for both human and Agent.'),
  },
  {
    num: '06',
    title: t('异步 Request-Reply', 'Async Request-Reply'),
    desc: t('Agent A 创建私有回复邮箱，发请求时带上 reply_to。Agent B 处理后将结果 SEND 到回复邮箱，A 随时 FETCH 取结果，不阻塞。', 'Agent A creates a private reply mailbox, includes reply_to. Agent B SENDs results there. A FETCHes when ready — no blocking.'),
  },
  {
    num: '07',
    title: t('Agent 注册与健康感知', 'Agent registration and health tracking'),
    desc: t('Worker 启动时 REGISTER，定期 REPORT 上报状态，主 Agent 通过 DISCOVER 列出所有在线 Worker，Worker 关闭时 UNREGISTER。', 'Workers REGISTER at startup, REPORT periodically, UNREGISTER at shutdown. Orchestrator uses DISCOVER to enumerate live workers.'),
  },
  {
    num: '08',
    title: t('告警广播', 'Alert broadcasting'),
    desc: t('检测方向共享邮箱发 critical 优先级告警，处理器 FETCH 拉取，即使临时离线也不会丢失告警。', 'Detectors publish critical alerts to a shared mailbox. Handlers FETCH — even if offline, alerts persist and are available on reconnect.'),
  },
])
</script>

<template>
  <div class="mq9-page">

    <!-- ── HERO ── -->
    <section class="mq9-hero">
      <div class="mq9-hero-inner">
        <div class="mq9-badge">
          <span class="mq9-badge-dot"></span>
          {{ t('Agent 注册中心 + 可靠异步通信', 'Agent Registry + Reliable Async Messaging') }}
        </div>

        <h1 class="mq9-title">
          <span class="mq9-title-name">mq9</span>
        </h1>

        <p class="mq9-title-sub">{{ t('专为 AI Agent 设计的 Broker', 'A broker built for AI Agents') }}</p>

        <p class="mq9-hero-desc">
          {{ t('mq9 将 Agent 注册、发现和可靠异步消息整合在同一个 broker 中，专为承载百万 Agent 而设计。让 Agent 之间的通信 just work。', 'mq9 provides Agent registration, discovery, and reliable asynchronous messaging in a single broker — designed to scale to millions of agents. Agent-to-agent communication, just works.') }}
        </p>

        <div class="mq9-hero-actions">
          <a class="mq9-btn-primary" :href="t('/zh/docs/', '/docs/')">
            {{ t('开始使用', 'Get Started') }} →
          </a>
          <a class="mq9-btn-ghost" :href="t('/zh/docs/protocol', '/docs/protocol')">
            {{ t('协议规范', 'Protocol Spec') }}
          </a>
          <a class="mq9-btn-ghost" href="https://github.com/robustmq/robustmq" target="_blank" rel="noopener">
            GitHub
          </a>
        </div>

        <div class="mq9-hero-note">
          {{ t('NATS 协议 · Python / Go / TypeScript / Java / Rust SDK · LangChain / LangGraph · MCP Server', 'NATS protocol · Python / Go / TypeScript / Java / Rust SDK · LangChain / LangGraph · MCP Server') }}
        </div>
      </div>
    </section>

    <!-- ── PROBLEM ── -->
    <section class="mq9-section">
      <div class="mq9-section-inner">
        <div class="mq9-problem">
          <div class="mq9-problem-text">
            <h2 class="mq9-section-title">{{ t('两个核心问题', 'Two Foundational Problems') }}</h2>
            <p>{{ t('任何多 Agent 系统，都会遇到同样的两个问题。', 'Every multi-agent system encounters the same two foundational problems.') }}</p>
            <p class="mq9-problem-item">
              <strong>{{ t('① Agent 之间如何找到彼此？', '① How do agents find each other?') }}</strong>
              {{ t('按 capability 发现，而不是硬编码地址。', 'Discovery by capability, not hardcoded addresses.') }}
            </p>
            <p class="mq9-problem-item">
              <strong>{{ t('② Agent 之间如何可靠地通信？', '② How do agents reliably communicate?') }}</strong>
              {{ t('Agent A 发消息时，Agent B 可能离线、正忙、或者还不存在。消息不能丢。', 'When Agent A sends, Agent B may be offline, busy, or not yet running. Messages cannot be lost.') }}
            </p>
            <p class="mq9-solution-line">{{ t('mq9 专门解决这两个问题，所以开发者可以专注于 Agent 逻辑，而不是基础设施。', 'mq9 solves exactly these two problems, so developers can focus on agent logic rather than infrastructure.') }}</p>
          </div>
          <div class="mq9-problem-compare">
            <div class="mq9-compare-item mq9-compare-bad">
              <div class="mq9-compare-label">{{ t('今天的做法', 'Today') }}</div>
              <div class="mq9-compare-rows">
                <div class="mq9-compare-row">
                  <span class="mq9-compare-icon">✗</span>
                  <span>{{ t('etcd + Kafka + 大量胶水代码', 'etcd + Kafka + lots of glue code') }}</span>
                </div>
                <div class="mq9-compare-row">
                  <span class="mq9-compare-icon">✗</span>
                  <span>{{ t('注册和消息是两个独立系统，状态不一致', 'Registry and messaging are separate systems, state diverges') }}</span>
                </div>
                <div class="mq9-compare-row">
                  <span class="mq9-compare-icon">✗</span>
                  <span>{{ t('HTTP 通信无法处理 Agent 离线', 'HTTP cannot handle Agent offline scenarios') }}</span>
                </div>
                <div class="mq9-compare-row">
                  <span class="mq9-compare-icon">✗</span>
                  <span>{{ t('每个团队重复造轮子', 'Every team rebuilds the same plumbing') }}</span>
                </div>
              </div>
            </div>
            <div class="mq9-compare-item mq9-compare-good">
              <div class="mq9-compare-label">mq9</div>
              <div class="mq9-compare-rows">
                <div class="mq9-compare-row">
                  <span class="mq9-compare-icon mq9-icon-ok">✓</span>
                  <span>{{ t('注册 + 消息，同一个 broker', 'Registry + messaging in one broker') }}</span>
                </div>
                <div class="mq9-compare-row">
                  <span class="mq9-compare-icon mq9-icon-ok">✓</span>
                  <span>{{ t('按 capability 语义发现 Agent', 'Discover agents by capability semantics') }}</span>
                </div>
                <div class="mq9-compare-row">
                  <span class="mq9-compare-icon mq9-icon-ok">✓</span>
                  <span>{{ t('离线照样收，重连后 FETCH', 'Offline delivery — messages wait in mailbox') }}</span>
                </div>
                <div class="mq9-compare-row">
                  <span class="mq9-compare-icon mq9-icon-ok">✓</span>
                  <span>{{ t('设计承载百万 Agent', 'Designed to scale to millions of agents') }}</span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>

    <!-- ── FLOW DIAGRAM ── -->
    <section class="mq9-section mq9-flow-section">
      <div class="mq9-section-inner">
        <img src="/flow.svg" alt="mq9 architecture flow" class="mq9-flow-img" />
      </div>
    </section>

    <!-- ── CAPABILITIES ── -->
    <section class="mq9-section mq9-primitives-section">
      <div class="mq9-section-inner mq9-primitives-inner">
        <div class="mq9-section-header">
          <div class="mq9-section-tag">{{ t('核心能力', 'Core Capabilities') }}</div>
          <h2 class="mq9-section-title">{{ t('注册发现 + 可靠异步通信', 'Registry & Discovery + Reliable Async Messaging') }}</h2>
        </div>
        <div class="mq9-primitives">
          <div v-for="p in capabilities" :key="p.title" class="mq9-primitive">
            <div class="mq9-primitive-header">
              <span class="mq9-primitive-icon">{{ p.icon }}</span>
              <div>
                <h3 class="mq9-primitive-title">{{ p.title }}</h3>
                <p class="mq9-primitive-subtitle">{{ p.subtitle }}</p>
              </div>
            </div>
            <pre class="mq9-code"><code>{{ p.code }}</code></pre>
          </div>
        </div>
      </div>
    </section>

    <!-- ── SCENARIOS ── -->
    <section class="mq9-section">
      <div class="mq9-section-inner">
        <div class="mq9-section-header">
          <div class="mq9-section-tag">{{ t('真实场景', 'Real Scenarios') }}</div>
          <h2 class="mq9-section-title">{{ t('八个真实使用场景', 'Eight real-world use cases') }}</h2>
        </div>
        <div class="mq9-scenarios">
          <div v-for="s in scenarios" :key="s.num" class="mq9-scenario">
            <div class="mq9-scenario-num">{{ s.num }}</div>
            <div>
              <h3 class="mq9-scenario-title">{{ s.title }}</h3>
              <p class="mq9-scenario-desc">{{ s.desc }}</p>
            </div>
          </div>
        </div>
      </div>
    </section>

    <!-- ── SDK ── -->
    <section class="mq9-section mq9-sdk-section">
      <div class="mq9-section-inner">
        <div class="mq9-section-header">
          <div class="mq9-section-tag">{{ t('接入方式', 'Integration') }}</div>
          <h2 class="mq9-section-title">{{ t('三种接入方式，按需选择', 'Three ways to connect — pick what fits') }}</h2>
        </div>
        <div class="mq9-sdk-cards">
          <div class="mq9-sdk-card">
            <div class="mq9-sdk-card-icon">🔌</div>
            <h3 class="mq9-sdk-card-title">{{ t('原生 NATS 客户端', 'Native NATS Client') }}</h3>
            <p class="mq9-sdk-card-desc">{{ t('mq9 基于 NATS 协议。任何语言的 NATS 客户端直接就是 mq9 的客户端，零依赖，零学习成本。', 'mq9 is built on NATS. Any NATS client in any language works out of the box — zero extra dependencies.') }}</p>
            <div class="mq9-langs">
              <span v-for="l in ['Go', 'Python', 'Rust', 'Java', 'JavaScript', 'C#', 'Ruby', 'Elixir']" :key="l" class="mq9-lang">{{ l }}</span>
            </div>
          </div>
          <div class="mq9-sdk-card mq9-sdk-card-featured">
            <div class="mq9-sdk-card-icon">📦</div>
            <h3 class="mq9-sdk-card-title">mq9 SDK</h3>
            <p class="mq9-sdk-card-desc">{{ t('官方 SDK，五种语言统一 API，类型安全，异步优先，内置 Priority 枚举、consume 循环和 Agent 注册方法。', 'Official SDK — five languages, unified API, type-safe, async-first. Typed Priority, consume loop, Agent registry methods.') }}</p>
            <div class="mq9-sdk-installs">
              <code>pip install mq9</code>
              <code>npm install mq9</code>
              <code>go get github.com/robustmq/mq9/go</code>
              <code>cargo add mq9</code>
            </div>
          </div>
          <div class="mq9-sdk-card">
            <div class="mq9-sdk-card-icon">🤖</div>
            <h3 class="mq9-sdk-card-title">{{ t('AI 框架集成', 'AI Framework Integration') }}</h3>
            <p class="mq9-sdk-card-desc">{{ t('官方 LangChain 工具包，8 个工具覆盖全部 mq9 操作，直接接入 LangChain Agent 和 LangGraph 工作流。原生 A2A 协议支持通过 mq9.a2a 接入。', 'Official LangChain toolkit — 8 tools covering all mq9 operations. Native A2A protocol support via mq9.a2a facade.') }}</p>
            <div class="mq9-sdk-installs">
              <code>pip install langchain-mq9</code>
              <code>pip install mq9[a2a]</code>
            </div>
            <div class="mq9-sdk-badges">
              <span class="mq9-sdk-badge">LangChain</span>
              <span class="mq9-sdk-badge">LangGraph</span>
              <span class="mq9-sdk-badge">A2A</span>
              <span class="mq9-sdk-badge">MCP Server</span>
            </div>
          </div>
        </div>
      </div>
    </section>

    <!-- ── PROTOCOL ── -->
    <section class="mq9-section">
      <div class="mq9-section-inner">
        <div class="mq9-section-header">
          <div class="mq9-section-tag">{{ t('协议总览', 'Protocol') }}</div>
          <h2 class="mq9-section-title">{{ t('完整的 Agent 通信协议', 'Complete Agent Communication Protocol') }}</h2>
          <p class="mq9-section-desc">{{ t('所有操作通过 NATS request/reply 完成，主题前缀 $mq9.AI.*。响应包含 error 字段，空字符串表示成功。', 'All operations use NATS request/reply under $mq9.AI.*. Responses include an error field; empty string means success.') }}</p>
        </div>
        <div class="mq9-proto-grid">
          <div class="mq9-proto-group">
            <div class="mq9-proto-group-label">{{ t('Agent 注册', 'Agent Registry') }}</div>
            <div class="mq9-proto-row">
              <code class="mq9-proto-subject">$mq9.AI.AGENT.REGISTER</code>
              <span class="mq9-proto-desc">{{ t('注册 Agent 及 AgentCard 能力描述', 'Register Agent with AgentCard capability description') }}</span>
            </div>
            <div class="mq9-proto-row">
              <code class="mq9-proto-subject">$mq9.AI.AGENT.DISCOVER</code>
              <span class="mq9-proto-desc">{{ t('全文检索 + 语义向量检索 Agent', 'Full-text + semantic vector search for Agents') }}</span>
            </div>
            <div class="mq9-proto-row">
              <code class="mq9-proto-subject">$mq9.AI.AGENT.REPORT</code>
              <span class="mq9-proto-desc">{{ t('Agent 状态上报 / 心跳', 'Agent status heartbeat') }}</span>
            </div>
            <div class="mq9-proto-row">
              <code class="mq9-proto-subject">$mq9.AI.AGENT.UNREGISTER</code>
              <span class="mq9-proto-desc">{{ t('关闭时注销 Agent', 'Unregister Agent at shutdown') }}</span>
            </div>
          </div>
          <div class="mq9-proto-group">
            <div class="mq9-proto-group-label">{{ t('邮箱与消息', 'Mailbox & Messaging') }}</div>
            <div class="mq9-proto-row">
              <code class="mq9-proto-subject">$mq9.AI.MAILBOX.CREATE</code>
              <span class="mq9-proto-desc">{{ t('创建持久化邮箱，声明 TTL', 'Create persistent mailbox, declare TTL') }}</span>
            </div>
            <div class="mq9-proto-row">
              <code class="mq9-proto-subject">$mq9.AI.MSG.SEND.{addr}</code>
              <span class="mq9-proto-desc">{{ t('发送消息，优先级通过 mq9-priority header 指定', 'Send message; priority via mq9-priority header') }}</span>
            </div>
            <div class="mq9-proto-row">
              <code class="mq9-proto-subject">$mq9.AI.MSG.FETCH.{addr}</code>
              <span class="mq9-proto-desc">{{ t('Pull 拉取消息，支持有状态/无状态消费', 'Pull messages; stateful or stateless') }}</span>
            </div>
            <div class="mq9-proto-row">
              <code class="mq9-proto-subject">$mq9.AI.MSG.ACK.{addr}</code>
              <span class="mq9-proto-desc">{{ t('ACK 推进消费位点，支持断点续拉', 'ACK to advance offset, enable resume-from-offset') }}</span>
            </div>
            <div class="mq9-proto-row">
              <code class="mq9-proto-subject">$mq9.AI.MSG.QUERY.{addr}</code>
              <span class="mq9-proto-desc">{{ t('查询消息，不影响消费位点', 'Query messages, offset unaffected') }}</span>
            </div>
            <div class="mq9-proto-row">
              <code class="mq9-proto-subject">$mq9.AI.MSG.DELETE.{addr}.{id}</code>
              <span class="mq9-proto-desc">{{ t('删除指定消息', 'Delete a specific message') }}</span>
            </div>
          </div>
          <div class="mq9-proto-group">
            <div class="mq9-proto-group-label">{{ t('消息 Header', 'Message Headers') }}</div>
            <div class="mq9-proto-row">
              <code class="mq9-proto-subject">mq9-priority: critical|urgent</code>
              <span class="mq9-proto-desc">{{ t('消息优先级，normal 为默认不填', 'Priority; normal is default (no header)') }}</span>
            </div>
            <div class="mq9-proto-row">
              <code class="mq9-proto-subject">mq9-key: {key}</code>
              <span class="mq9-proto-desc">{{ t('同 key 只保留最新一条（去重压实）', 'Keep only latest per key (dedup compaction)') }}</span>
            </div>
            <div class="mq9-proto-row">
              <code class="mq9-proto-subject">mq9-delay: {seconds}</code>
              <span class="mq9-proto-desc">{{ t('延迟投递，指定秒数后消息才可见', 'Delay visibility by N seconds') }}</span>
            </div>
            <div class="mq9-proto-row">
              <code class="mq9-proto-subject">mq9-ttl: {seconds}</code>
              <span class="mq9-proto-desc">{{ t('消息级 TTL，独立于邮箱 TTL', 'Per-message TTL, independent of mailbox TTL') }}</span>
            </div>
            <div class="mq9-proto-row">
              <code class="mq9-proto-subject">mq9-tags: tag1,tag2</code>
              <span class="mq9-proto-desc">{{ t('标签，可通过 QUERY 过滤', 'Tags, filterable via QUERY') }}</span>
            </div>
          </div>
        </div>
      </div>
    </section>

    <!-- ── CTA ── -->
    <section class="mq9-section mq9-cta-section">
      <div class="mq9-section-inner">
        <div class="mq9-cta">
          <h2 class="mq9-cta-title">{{ t('开始构建', 'Start Building') }}</h2>
          <p class="mq9-cta-desc">{{ t('连接公共演示服务器——无需本地部署。', 'Connect to the public demo server — no local setup required.') }}</p>
          <pre class="mq9-code mq9-cta-code"><code>export NATS_URL=nats://demo.robustmq.com:4222

# Register your Agent
nats request '$mq9.AI.AGENT.REGISTER' \
  '{"name":"my.agent","mailbox":"my.inbox","payload":"My Agent capabilities"}'

# Create a mailbox
nats request '$mq9.AI.MAILBOX.CREATE' '{"name":"my.inbox","ttl":3600}'

# Send a message
nats request '$mq9.AI.MSG.SEND.my.inbox' \
  --header 'mq9-priority:urgent' \
  '{"task":"summarize dataset A"}'

# FETCH (resumes from last ACK)
nats request '$mq9.AI.MSG.FETCH.my.inbox' \
  '{"group_name":"worker","deliver":"earliest"}'</code></pre>
          <div class="mq9-cta-links">
            <a class="mq9-btn-primary" :href="t('/zh/docs/', '/docs/')">{{ t('查看文档', 'Read the Docs') }}</a>
            <a class="mq9-btn-ghost" href="https://github.com/robustmq/robustmq" target="_blank" rel="noopener">GitHub</a>
          </div>
        </div>
      </div>
    </section>

  </div>
</template>

<style scoped>
.mq9-page {
  min-height: 100vh;
  background: #ffffff;
  color: #000000;
  font-family: inherit;
}

/* ── Hero ── */
.mq9-hero {
  position: relative;
  padding: 100px 24px 80px;
  text-align: center;
  overflow: hidden;
}
.mq9-hero-inner {
  position: relative;
  max-width: 760px;
  margin: 0 auto;
  display: flex;
  flex-direction: column;
  align-items: center;
}
.mq9-badge {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 6px 16px;
  border-radius: 20px;
  border: 1px solid #d4d4d4;
  background: #f5f5f5;
  color: #555555;
  font-size: 12px;
  margin-bottom: 28px;
}
.mq9-badge-dot {
  width: 6px; height: 6px;
  border-radius: 50%;
  background: #000000;
  animation: pulse 2s infinite;
}
@keyframes pulse {
  0%,100% { opacity:1; transform:scale(1); }
  50% { opacity:0.4; transform:scale(1.4); }
}
.mq9-title {
  margin: 0 0 12px;
  line-height: 1;
}
.mq9-title-name {
  font-size: clamp(72px, 14vw, 120px);
  font-weight: 900;
  letter-spacing: -0.03em;
  color: #000000;
}
.mq9-title-sub {
  font-size: 18px;
  color: #666666;
  margin: 0 0 20px;
}
.mq9-hero-desc {
  font-size: 16px;
  line-height: 1.7;
  color: #444444;
  max-width: 600px;
  margin: 0 0 32px;
}
.mq9-hero-actions {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
  justify-content: center;
  margin-bottom: 20px;
}
.mq9-btn-primary {
  padding: 11px 28px;
  border-radius: 8px;
  background: #000000;
  color: #ffffff;
  font-weight: 600;
  font-size: 14px;
  text-decoration: none;
  transition: opacity 0.2s, transform 0.15s;
}
.mq9-btn-primary:hover { opacity: 0.75; transform: translateY(-1px); }
.mq9-btn-ghost {
  padding: 11px 28px;
  border-radius: 8px;
  border: 1px solid #d4d4d4;
  color: #333333;
  font-weight: 600;
  font-size: 14px;
  text-decoration: none;
  transition: border-color 0.2s, background 0.2s;
}
.mq9-btn-ghost:hover { border-color: #000000; background: #f5f5f5; }
.mq9-hero-note {
  font-size: 12px;
  color: #999999;
}

/* ── Section ── */
.mq9-section { padding: 72px 24px; }
.mq9-section-inner { max-width: 1000px; margin: 0 auto; }
.mq9-primitives-inner { max-width: 1400px; }
.mq9-section-header { text-align: center; margin-bottom: 48px; }
.mq9-section-tag {
  display: inline-block;
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  color: #555555;
  padding: 4px 12px;
  border-radius: 20px;
  border: 1px solid #d4d4d4;
  background: #f5f5f5;
  margin-bottom: 14px;
}
.mq9-section-title {
  font-size: clamp(22px, 4vw, 32px);
  font-weight: 700;
  color: #000000;
  margin: 0 0 12px;
}
.mq9-section-desc {
  font-size: 15px;
  color: #666666;
  max-width: 600px;
  margin: 0 auto;
  line-height: 1.6;
}

/* ── Problem ── */
.mq9-problem {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 48px;
  align-items: start;
}
.mq9-problem-text p { color: #666666; line-height: 1.7; margin: 0 0 14px; font-size: 15px; }
.mq9-problem-item strong { color: #000000; display: block; margin-bottom: 4px; }
.mq9-solution-line { color: #000000 !important; font-weight: 600; }
.mq9-problem-compare { display: flex; flex-direction: column; gap: 16px; }
.mq9-compare-item {
  padding: 20px;
  border-radius: 12px;
  border: 1px solid #e5e5e5;
}
.mq9-compare-bad { background: #fafafa; }
.mq9-compare-good { background: #f5f5f5; border-color: #d4d4d4; }
.mq9-compare-label { font-size: 11px; font-weight: 700; color: #999999; margin-bottom: 12px; text-transform: uppercase; letter-spacing: 0.08em; }
.mq9-compare-rows { display: flex; flex-direction: column; gap: 8px; }
.mq9-compare-row { display: flex; align-items: flex-start; gap: 10px; font-size: 13px; color: #555555; line-height: 1.5; }
.mq9-compare-icon { flex-shrink: 0; font-style: normal; color: #bbbbbb; font-weight: 700; width: 14px; }
.mq9-icon-ok { color: #000000; }

/* ── Primitives ── */
.mq9-primitives-section { background: #f5f5f5; }
.mq9-primitives { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); grid-auto-rows: 1fr; gap: 16px; }
.mq9-primitive {
  padding: 20px;
  border-radius: 14px;
  border: 1px solid #e5e5e5;
  background: #ffffff;
  display: flex;
  flex-direction: column;
  gap: 12px;
  transition: border-color 0.2s, box-shadow 0.2s;
  min-width: 0;
  overflow: hidden;
}
.mq9-primitive .mq9-code { flex: 1; }
.mq9-primitive:hover { border-color: #000000; box-shadow: 0 4px 16px rgba(0,0,0,0.06); }
.mq9-primitive-header { display: flex; align-items: flex-start; gap: 12px; }
.mq9-primitive-icon { font-size: 28px; flex-shrink: 0; }
.mq9-primitive-title { font-size: 17px; font-weight: 700; color: #000000; margin: 0 0 2px; }
.mq9-primitive-subtitle { font-size: 12px; color: #999999; margin: 0; }
.mq9-code {
  background: #f5f5f5;
  border: 1px solid #e5e5e5;
  border-radius: 8px;
  padding: 14px 16px;
  font-size: 12px;
  line-height: 1.6;
  color: #333333;
  overflow-x: auto;
  margin: 0;
  white-space: pre;
}
.mq9-code code { font-family: 'JetBrains Mono', 'Fira Code', monospace; background: none; color: inherit; }

/* ── Scenarios ── */
.mq9-scenarios { display: grid; grid-template-columns: repeat(2, 1fr); gap: 20px; }
.mq9-scenario {
  display: flex;
  gap: 16px;
  padding: 20px;
  border-radius: 12px;
  border: 1px solid #e5e5e5;
  background: #fafafa;
}
.mq9-scenario-num {
  font-size: 28px;
  font-weight: 900;
  color: #e5e5e5;
  line-height: 1;
  flex-shrink: 0;
  font-variant-numeric: tabular-nums;
}
.mq9-scenario-title { font-size: 15px; font-weight: 600; color: #000000; margin: 0 0 6px; }
.mq9-scenario-desc { font-size: 13px; color: #666666; line-height: 1.6; margin: 0; }

/* ── SDK ── */
.mq9-sdk-section { background: #f5f5f5; }
.mq9-sdk-cards {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 20px;
}
.mq9-sdk-card {
  background: #ffffff;
  border: 1px solid #e5e5e5;
  border-radius: 16px;
  padding: 28px 24px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.mq9-sdk-card-featured { border-color: #000000; }
.mq9-sdk-card-icon { font-size: 28px; }
.mq9-sdk-card-title { font-size: 17px; font-weight: 700; color: #000000; margin: 0; }
.mq9-sdk-card-desc { font-size: 14px; color: #666666; line-height: 1.6; margin: 0; flex: 1; }
.mq9-langs { display: flex; flex-wrap: wrap; gap: 8px; }
.mq9-lang {
  padding: 4px 12px;
  border-radius: 20px;
  border: 1px solid #d4d4d4;
  background: #f5f5f5;
  color: #333333;
  font-size: 12px;
  font-weight: 600;
}
.mq9-sdk-installs { display: flex; flex-direction: column; gap: 6px; }
.mq9-sdk-installs code {
  font-family: 'JetBrains Mono', 'Fira Code', monospace;
  font-size: 12px;
  background: #f5f5f5;
  border: 1px solid #e5e5e5;
  border-radius: 6px;
  padding: 5px 10px;
  color: #000000;
  display: block;
}
.mq9-sdk-badges { display: flex; flex-wrap: wrap; gap: 8px; }
.mq9-sdk-badge {
  padding: 3px 10px;
  border-radius: 12px;
  font-size: 11px;
  font-weight: 700;
  background: #f0f0f0;
  border: 1px solid #d4d4d4;
  color: #333333;
}

/* ── Protocol grid ── */
.mq9-proto-grid { display: flex; flex-direction: column; gap: 28px; }
.mq9-proto-group { display: flex; flex-direction: column; gap: 6px; }
.mq9-proto-group-label {
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  color: #555555;
  margin-bottom: 4px;
}
.mq9-proto-row {
  display: flex;
  align-items: baseline;
  gap: 16px;
  padding: 8px 14px;
  border-radius: 8px;
  background: #fafafa;
  border: 1px solid #e5e5e5;
  flex-wrap: wrap;
}
.mq9-proto-subject {
  font-family: 'JetBrains Mono', 'Fira Code', monospace;
  font-size: 12px;
  color: #000000;
  background: #f0f0f0;
  border: 1px solid #d4d4d4;
  padding: 2px 8px;
  border-radius: 4px;
  flex-shrink: 0;
  white-space: nowrap;
}
.mq9-proto-desc { font-size: 13px; color: #666666; flex: 1; }

/* ── CTA ── */
.mq9-cta-section { background: #f5f5f5; }
.mq9-cta { text-align: center; max-width: 680px; margin: 0 auto; }
.mq9-cta-title { font-size: 28px; font-weight: 700; color: #000000; margin: 0 0 12px; }
.mq9-cta-desc { font-size: 15px; color: #666666; margin: 0 0 24px; }
.mq9-cta-code { text-align: left; margin-bottom: 28px; }
.mq9-cta-links { display: flex; gap: 12px; justify-content: center; flex-wrap: wrap; }

/* ── Flow diagram ── */
.mq9-flow-section { padding: 0 24px 72px; }
.mq9-flow-img {
  width: 100%;
  display: block;
  border: 1px solid #e5e5e5;
  border-radius: 12px;
}

/* ── Responsive ── */
@media (max-width: 900px) {
  .mq9-sdk-cards { grid-template-columns: 1fr; }
}
@media (max-width: 768px) {
  .mq9-hero { padding: 72px 20px 60px; }
  .mq9-problem { grid-template-columns: 1fr; }
  .mq9-primitives { grid-template-columns: 1fr; }
  .mq9-scenarios { grid-template-columns: 1fr; }
  .mq9-section { padding: 48px 20px; }
}
</style>
