package io.mq9.a2a;

import java.util.concurrent.CompletableFuture;

/**
 * Receives A2A response events from the {@link MessageHandler} and forwards
 * each one to the caller's {@code reply_to} mailbox in real time (streaming).
 *
 * <p>The handler calls {@link #enqueue} for each event in the A2A sequence:
 * <pre>
 *   TaskStatusUpdateEvent(WORKING)
 *   TaskArtifactUpdateEvent(...)   // may be called multiple times
 *   TaskStatusUpdateEvent(COMPLETED | FAILED | CANCELED)
 * </pre>
 *
 * <p>The framework sends a terminal "last" marker automatically after the
 * handler returns.
 */
public interface EventQueue {

    /**
     * Enqueues an A2A event. The event is serialised and forwarded to the
     * caller's mailbox immediately.
     *
     * @param event a protobuf/spec event object —
     *              {@code TaskStatusUpdateEvent} or {@code TaskArtifactUpdateEvent}
     */
    CompletableFuture<Void> enqueue(Object event);
}
