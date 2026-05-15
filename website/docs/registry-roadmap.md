---
title: Agent Registry — Vision and Capability Roadmap
description: Where mq9's Agent Registry is going, why, and how it fits into the broader A2A ecosystem. Three capability tiers from MVP to enterprise-grade.
outline: deep
---

# Agent Registry — Vision and Roadmap

## What Problem This Solves

Async messaging between agents only works if agents can find each other first. A message queue without a registry forces every caller to hardcode endpoints, maintain their own address books, and handle churn manually. The registry is the address book that the messaging layer consumes.

mq9 ships both layers as a single open-source system: find the agent, then talk to it reliably. This document covers the registry side — what it does today, what it needs to become a production-grade system, and the long-term direction.

---

## Industry Context

The agent registry problem is being solved in several independent directions simultaneously. Understanding the landscape explains the choices mq9 makes.

### How the ecosystem is approaching this

Five significant efforts are underway as of mid-2025:

**MCP Registry** takes a centralized approach: a Go REST API with GitHub OAuth for authentication and DNS TXT records for ownership verification. Simple to operate; single point of trust.

**A2A Agent Cards** go the opposite direction. Each agent self-publishes a machine-readable descriptor at `/.well-known/agent.json`. No central authority. Discovery is federated by definition — any crawler or index can consume it.

**AGNTCY Agent Discovery Service (ADS)** uses IPFS Kademlia DHT for peer-to-peer routing, OCI artifacts as the package format, and Sigstore for supply-chain integrity. Maximally decentralized; operationally complex.

**Microsoft Entra Agent ID** treats agents as first-class principals in the enterprise identity graph. Registry is a byproduct of identity management. Requires Azure AD.

**NANDA Index** uses Ed25519-signed `AgentAddr` records in a three-layer design: cryptographic identity, semantic metadata, and routing. The signing model is borrowed from DNSSEC concepts.

### What the research says about registry quality

ArXiv 2508.03095 identifies four evaluation dimensions: Security, Authentication, Scalability, and Maintenance. It frames trust around three pillars: Identity Assurance (you know who registered this agent), Integrity Verification (the descriptor has not been tampered with), and Privacy Preservation (discovery does not leak internal topology).

### The A2A discussion on governance

Google's A2A Discussion #741 (kthota-g, June 2025) proposes a formal governance model with four roles — Administrator, Catalog Manager, User, and Viewer — alongside concepts like Agent Entitlements (access control at the catalog level), Open Discovery, and Agent Search. It also references W3C DCAT v3 as a candidate metadata vocabulary for interoperability.

### Three evolutionary stages

Registry implementations across the industry follow a recognizable pattern:

1. **Static files** — Agent Cards at well-known URLs, no query capability, no lifecycle management.
2. **Dynamic REST API** — Centralized registry with CRUD, search, TTL, auth. Operationally simple; requires trusting the operator.
3. **Decentralized cryptographically verifiable registry** — Signed provenance, DID-based identity, content-addressed storage. Maximum trustlessness; significant operational overhead.

Most production systems today operate at stage 2. Stage 3 infrastructure is emerging but not yet stable enough for general use.

---

## mq9 Positioning

mq9 is not trying to solve every registry problem. The explicit scope:

- Mid-scale, out-of-the-box deployment. No Kubernetes operator required to get started.
- A2A-compatible. mq9 must be able to consume A2A AgentCards from `/.well-known/agent.json` and auto-onboard those agents. This is the entry ticket into the broader A2A ecosystem.
- Apache-governed open source. No enterprise license required for any feature in this roadmap.

What mq9 is **not** building:

- An enterprise governance layer (Entra-style identity, RBAC hierarchies, compliance reporting).
- A decentralized identity layer (DID resolution, on-chain provenance, IPFS-backed storage).

The goal is: "let agents find each other before communicating, done to industrial grade." Everything else is out of scope until the core is solid.

---

## Capability Tiers

The roadmap is organized into three tiers. Tier 1 is required for any production use. Tier 2 is required for a mature product. Tier 3 addresses enterprise and research-grade requirements.

Tiers are not strictly sequential. Some Tier 2 work (semantic search) is already partially in place. The ordering reflects priority, not a delivery schedule.

### Tier 1 — MVP

These capabilities are required before mq9 registry can be recommended for any production deployment.

#### Agent Card data model

Every registered agent must have a structured descriptor with at minimum:

- `id` — globally unique identifier (UUID or URI)
- `name` — human-readable name
- `version` — semver string
- `capability_description` — free-text description of what the agent does
- `endpoint` — where to reach the agent (URL or mq9 mail address)
- `auth_schemes` — list of supported authentication methods
- `metadata` — arbitrary key-value pairs for caller use
- `tags` — indexed labels for categorical filtering

This schema is compatible with the A2A AgentCard structure so that agents registered via `/.well-known/agent.json` can be imported without field mapping.

#### Lifecycle operations

REGISTER, DEREGISTER, UPDATE, and versioning. When an agent is updated, the previous version record must be retained for auditability. Clients querying by name should receive the latest version by default, with the ability to request a specific version.

#### Multi-dimensional query

The registry is only useful if agents can be found efficiently. Required query dimensions:

- By name (exact and prefix match)
- By capability description (full-text search)
- By tag (set intersection)
- By owner or team
- By semantic similarity (embedding-based nearest-neighbor on capability descriptions)

#### Heartbeat and auto-expiry

Agents must send periodic heartbeats via `AGENT.REPORT`. If no heartbeat arrives within the configured TTL window, the registry marks the agent as unavailable and removes it from query results. This prevents stale entries from accumulating and ensures that DISCOVER only returns agents that are actually running.

#### Basic authentication

Registration and query endpoints must require authentication. Acceptable schemes at this tier: OAuth 2.0 (client credentials flow) or API key. Unauthenticated writes must be rejected.

#### Persistent storage

Registry state must survive broker restarts. This is the minimum durability requirement. High availability (replication, failover) is Tier 2.

#### A2A compatibility

mq9 must be able to fetch `/.well-known/agent.json` from a given URL, parse the A2A AgentCard, and register the agent into the mq9 registry automatically. This enables mq9 to participate in the broader A2A ecosystem without requiring agents to adopt a new registration protocol.

---

### Tier 2 — Mature Product

Tier 2 capabilities are required for mq9 to be recommended for team-scale or production-critical deployments.

#### Semantic search

Full-text search on capability descriptions is insufficient when agent names and descriptions use different vocabulary than the query. Semantic search using vector embeddings (e.g., stored in a sidecar vector index) allows callers to describe what they need in natural language and receive relevant results even when keyword overlap is low.

This is partially operational today; the roadmap item is to stabilize the API, document the embedding model requirements, and ensure it scales alongside the registry size.

#### Entitlement model

Not every agent should be discoverable by every caller. The entitlement model defines which clients (identified by their auth principal) can see and invoke which agents. This is the capability described in A2A Discussion #741 as "Agent Entitlements."

The model does not need to be complex at this tier: a simple allow-list per agent (principals that can discover and call it) covers most use cases.

#### Audit log

Every REGISTER, DEREGISTER, UPDATE, and DISCOVER operation should be logged with timestamp, principal, and operation details. This is required for any deployment where you need to know who registered what and when.

#### Lifecycle management

Agents go through stages: registered, active, deprecated, revoked. Tier 2 adds explicit state transitions and the ability to mark an agent as deprecated (still discoverable, but with a deprecation notice) or revoked (not discoverable, not callable).

Versioning at this tier means: multiple versions of the same agent can coexist in the registry. Callers can pin to a version or request the latest stable.

#### Federation

Cross-registry discovery: a mq9 registry instance can be configured to forward unresolved queries to a peer registry. This allows a team-local registry to fall back to an organization-level registry for agents it does not host.

Federation at this tier is simple: a static list of upstream registries, tried in order. It does not require a distributed protocol.

#### High availability

The registry must remain available during single-node failures. This requires replication of registry state and leader election. The specific mechanism (Raft, primary-replica, etc.) is an implementation detail; the observable requirement is: no single point of failure.

---

### Tier 3 — Enterprise Deepening

Tier 3 addresses requirements that arise at large-scale enterprise deployments or in high-security environments. These are long-term items — there is no committed timeline.

#### Cryptographic integrity

Agent descriptors should be signed by the registering principal so that consumers can verify that the descriptor has not been tampered with after registration. This aligns with AGNTCY ADS's use of Sigstore and NANDA Index's use of Ed25519.

Longer term: support for W3C Verifiable Credentials (W3C VC) as the signing and provenance format, enabling interoperability with the broader decentralized identity ecosystem.

#### Privacy-preserving discovery

Some deployments need selective disclosure: an agent should be discoverable to authorized callers without exposing its full descriptor to everyone. This may use attribute-based access control on query results, or zero-knowledge techniques for capability proofs. The research framing is ArXiv 2508.03095's "Privacy Preservation" pillar.

#### Security scanning at registration time

When an agent registers, its endpoint and descriptor can be scanned for known vulnerability patterns, malformed payloads, or suspicious metadata. This is particularly relevant for open registries where any agent can self-register.

#### DID and decentralized identity

Support for Decentralized Identifiers (DID) as agent identifiers, enabling agents to prove their identity without relying on mq9 as the root of trust. This makes the registry a cache and index rather than the authoritative identity source.

#### Cross-region federation

Tier 2 federation is static and local. Tier 3 federation spans geographic regions with consistency guarantees: a discovery query anywhere returns the same result within a bounded staleness window.

#### OpenTelemetry integration

Native export of registry operation traces and metrics via OpenTelemetry, enabling operators to correlate registry activity with the broader observability stack.

---

## What This Means for Integrators

If you are building on mq9 today:

- The Tier 1 data model (Agent Card schema, REGISTER/DISCOVER/REPORT/UNREGISTER) is stable. Build against it.
- Semantic search is available but the API surface may change before it stabilizes in Tier 2.
- A2A compatibility (consuming `/.well-known/agent.json`) is a hard requirement — mq9 will always support this.
- The entitlement model does not exist yet. If you need access control on discovery today, implement it at the application layer.

The registry and the messaging layer share the same broker. Agents discovered via the registry communicate via mq9 mailboxes. There is no separate service to run.
