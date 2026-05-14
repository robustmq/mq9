package io.mq9;

import java.util.function.BiConsumer;

/**
 * Options for {@link Mq9Client#consume}.
 */
public final class ConsumeOptions {

    /** Consumer group name (forwarded to every fetch). */
    public final String groupName;

    /** Delivery start point passed to the first fetch. Default {@code "latest"}. */
    public final String deliver;

    /** Messages requested per fetch batch. Default 10. */
    public final int numMsgs;

    /** Server-side wait time per fetch in ms. Default 500. */
    public final long maxWaitMs;

    /**
     * When {@code true} (default) the client sends an ACK after a successful
     * handler invocation. When {@code false} the application is responsible
     * for calling {@link Mq9Client#ack}.
     */
    public final boolean autoAck;

    /**
     * Called on the consume loop thread when the handler completes
     * exceptionally. Receives the offending message and the exception.
     * If null, the error is only logged.
     */
    public final BiConsumer<Message, Throwable> errorHandler;

    private ConsumeOptions(Builder b) {
        this.groupName = b.groupName;
        this.deliver = b.deliver;
        this.numMsgs = b.numMsgs;
        this.maxWaitMs = b.maxWaitMs;
        this.autoAck = b.autoAck;
        this.errorHandler = b.errorHandler;
    }

    public static Builder builder() {
        return new Builder();
    }

    public static final class Builder {
        private String groupName;
        private String deliver = "latest";
        private int numMsgs = 10;
        private long maxWaitMs = 500;
        private boolean autoAck = true;
        private BiConsumer<Message, Throwable> errorHandler;

        public Builder groupName(String groupName) {
            this.groupName = groupName;
            return this;
        }

        public Builder deliver(String deliver) {
            this.deliver = deliver;
            return this;
        }

        public Builder numMsgs(int numMsgs) {
            this.numMsgs = numMsgs;
            return this;
        }

        public Builder maxWaitMs(long maxWaitMs) {
            this.maxWaitMs = maxWaitMs;
            return this;
        }

        public Builder autoAck(boolean autoAck) {
            this.autoAck = autoAck;
            return this;
        }

        public Builder errorHandler(BiConsumer<Message, Throwable> errorHandler) {
            this.errorHandler = errorHandler;
            return this;
        }

        public ConsumeOptions build() {
            return new ConsumeOptions(this);
        }
    }
}
