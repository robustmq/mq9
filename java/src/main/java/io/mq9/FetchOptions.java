package io.mq9;

/**
 * Options for a single {@link Mq9Client#fetch} call.
 */
public final class FetchOptions {

    /**
     * Consumer group name. When set the broker advances the group's offset
     * and subsequent fetches continue from where they left off.
     * Null means stateless delivery.
     */
    public final String groupName;

    /**
     * Delivery start point: {@code "latest"} (default) or {@code "earliest"}.
     */
    public final String deliver;

    /** Fetch from this Unix timestamp (seconds); null means omit. */
    public final Long fromTime;

    /** Fetch starting from this msg_id; null means omit. */
    public final Long fromId;

    /** Force re-delivery of already-acknowledged messages. */
    public final boolean forceDeliver;

    /** Maximum number of messages per fetch (server default 100). */
    public final int numMsgs;

    /** How long (ms) the server waits before returning an empty list. */
    public final long maxWaitMs;

    private FetchOptions(Builder b) {
        this.groupName = b.groupName;
        this.deliver = b.deliver;
        this.fromTime = b.fromTime;
        this.fromId = b.fromId;
        this.forceDeliver = b.forceDeliver;
        this.numMsgs = b.numMsgs;
        this.maxWaitMs = b.maxWaitMs;
    }

    public static Builder builder() {
        return new Builder();
    }

    public static final class Builder {
        private String groupName;
        private String deliver = "latest";
        private Long fromTime;
        private Long fromId;
        private boolean forceDeliver = false;
        private int numMsgs = 100;
        private long maxWaitMs = 500;

        public Builder groupName(String groupName) {
            this.groupName = groupName;
            return this;
        }

        public Builder deliver(String deliver) {
            this.deliver = deliver;
            return this;
        }

        public Builder fromTime(long fromTime) {
            this.fromTime = fromTime;
            return this;
        }

        public Builder fromId(long fromId) {
            this.fromId = fromId;
            return this;
        }

        public Builder forceDeliver(boolean forceDeliver) {
            this.forceDeliver = forceDeliver;
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

        public FetchOptions build() {
            return new FetchOptions(this);
        }
    }
}
