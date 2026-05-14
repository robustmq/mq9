package io.mq9;

import java.util.concurrent.CompletableFuture;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicLong;

/**
 * Handle for a running consume loop started by {@link Mq9Client#consume}.
 *
 * <p>The loop runs asynchronously on a virtual thread (Java 21+) or a platform
 * thread and can be stopped gracefully via {@link #stop()}.
 */
public final class Consumer {

    private final AtomicBoolean running;
    private final AtomicLong processedCount;
    private final CompletableFuture<Void> doneFuture;

    Consumer(AtomicBoolean running, AtomicLong processedCount, CompletableFuture<Void> doneFuture) {
        this.running = running;
        this.processedCount = processedCount;
        this.doneFuture = doneFuture;
    }

    /** Returns {@code true} while the consume loop is active. */
    public boolean isRunning() {
        return running.get();
    }

    /** Total number of messages successfully handled (handler completed without error). */
    public long getProcessedCount() {
        return processedCount.get();
    }

    /**
     * Signals the loop to stop and returns a future that completes when the
     * loop has actually exited.  Safe to call multiple times.
     */
    public CompletableFuture<Void> stop() {
        running.set(false);
        return doneFuture;
    }
}
