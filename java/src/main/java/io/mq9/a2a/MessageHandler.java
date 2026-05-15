package io.mq9.a2a;

import java.util.concurrent.CompletableFuture;

/**
 * Functional interface for handling incoming A2A messages.
 *
 * <p>Register via {@link Mq9A2AAgent#onMessage}:
 * <pre>{@code
 * agent.onMessage((context, queue) -> {
 *     // A2A protocol: WORKING → Artifact(s) → COMPLETED
 *     return queue.enqueue(new TaskStatusUpdateEvent(...WORKING...))
 *         .thenCompose(v -> queue.enqueue(new TaskArtifactUpdateEvent(...)))
 *         .thenCompose(v -> queue.enqueue(new TaskStatusUpdateEvent(...COMPLETED...)));
 * });
 * }</pre>
 */
@FunctionalInterface
public interface MessageHandler {

    /**
     * Called for each incoming message.
     *
     * @param context carries the incoming message and task metadata
     * @param queue   push response events here; the framework forwards them to
     *                the caller's mailbox in real time
     * @return a future that completes when the handler is done
     */
    CompletableFuture<Void> handle(A2AContext context, EventQueue queue);
}
