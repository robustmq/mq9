package io.mq9.a2a;

import java.util.concurrent.CompletableFuture;
import java.util.concurrent.atomic.AtomicBoolean;

/**
 * Forwards each enqueued A2A event to the caller's {@code reply_to} mailbox
 * immediately (streaming). Tracks whether a final event was sent so the
 * framework can send a terminal marker if the handler returns without one.
 */
final class ForwardingEventQueue implements EventQueue {

    private final Mq9A2AAgent agent;
    private final String      replyTo;
    private final String      taskId;
    private final AtomicBoolean lastSent = new AtomicBoolean(false);

    ForwardingEventQueue(Mq9A2AAgent agent, String replyTo, String taskId) {
        this.agent   = agent;
        this.replyTo = replyTo;
        this.taskId  = taskId;
    }

    /**
     * Sends the event to the reply mailbox. If the event is a final-state
     * {@code TaskStatusUpdateEvent} the "last" flag is set automatically.
     */
    @Override
    public CompletableFuture<Void> enqueue(Object event) {
        if (replyTo == null) return CompletableFuture.completedFuture(null);

        boolean isLast = isFinalEvent(event);
        if (isLast) lastSent.set(true);

        return agent.sendEvent(replyTo, event, taskId, isLast);
    }

    /**
     * Called by the framework after the handler completes. Sends a COMPLETED
     * sentinel if the handler never enqueued a final event.
     */
    CompletableFuture<Void> flushLast() {
        if (replyTo == null || lastSent.get()) {
            return CompletableFuture.completedFuture(null);
        }
        lastSent.set(true);
        io.a2a.spec.TaskStatusUpdateEvent sentinel = new io.a2a.spec.TaskStatusUpdateEvent.Builder()
                .taskId(taskId)
                .status(new io.a2a.spec.TaskStatus(io.a2a.spec.TaskState.COMPLETED))
                .isFinal(true)
                .build();
        return agent.sendEvent(replyTo, sentinel, taskId, true);
    }

    // ── helpers ───────────────────────────────────────────────────────────────

    private static boolean isFinalEvent(Object event) {
        if (event instanceof io.a2a.spec.TaskStatusUpdateEvent e) {
            return e.isFinal();
        }
        return false;
    }
}
