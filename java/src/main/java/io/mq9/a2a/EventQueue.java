package io.mq9.a2a;

import io.a2a.spec.Artifact;
import io.a2a.spec.TaskArtifactUpdateEvent;
import io.a2a.spec.TaskState;
import io.a2a.spec.TaskStatus;
import io.a2a.spec.TaskStatusUpdateEvent;
import io.a2a.spec.TextPart;

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
     * @param event {@code TaskStatusUpdateEvent} or {@code TaskArtifactUpdateEvent}
     */
    CompletableFuture<Void> enqueue(Object event);

    // ── Helper methods — avoid constructing Builder chains in every handler ──

    /** Sends {@code TaskStatusUpdateEvent(WORKING)}. */
    default CompletableFuture<Void> working(A2AContext ctx) {
        return enqueue(new TaskStatusUpdateEvent.Builder()
                .taskId(ctx.taskId)
                .contextId(ctx.contextId)
                .status(new TaskStatus(TaskState.WORKING))
                .isFinal(false)
                .build());
    }

    /**
     * Sends a {@code TaskArtifactUpdateEvent} with a single text part.
     *
     * @param name   artifact name
     * @param text   result text
     */
    default CompletableFuture<Void> artifact(A2AContext ctx, String name, String text) {
        return enqueue(new TaskArtifactUpdateEvent.Builder()
                .taskId(ctx.taskId)
                .contextId(ctx.contextId)
                .artifact(new Artifact.Builder()
                        .name(name)
                        .parts(new TextPart(text))
                        .build())
                .lastChunk(true)
                .build());
    }

    /** Sends {@code TaskStatusUpdateEvent(COMPLETED)} as the final event. */
    default CompletableFuture<Void> completed(A2AContext ctx) {
        return enqueue(new TaskStatusUpdateEvent.Builder()
                .taskId(ctx.taskId)
                .contextId(ctx.contextId)
                .status(new TaskStatus(TaskState.COMPLETED))
                .isFinal(true)
                .build());
    }

    /** Sends {@code TaskStatusUpdateEvent(FAILED)} as the final event. */
    default CompletableFuture<Void> failed(A2AContext ctx) {
        return enqueue(new TaskStatusUpdateEvent.Builder()
                .taskId(ctx.taskId)
                .contextId(ctx.contextId)
                .status(new TaskStatus(TaskState.FAILED))
                .isFinal(true)
                .build());
    }
}
