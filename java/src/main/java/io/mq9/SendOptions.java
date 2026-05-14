package io.mq9;

import java.util.List;

/**
 * Optional parameters for {@link Mq9Client#send}.
 */
public final class SendOptions {

    public final Priority priority;
    /** Deduplication key — broker drops duplicates with the same key. */
    public final String key;
    /** Delay delivery by this many seconds. Returns msg_id -1. */
    public final Long delay;
    /** Message TTL in seconds; 0 or null means broker default. */
    public final Long ttl;
    public final List<String> tags;

    private SendOptions(Builder b) {
        this.priority = b.priority;
        this.key = b.key;
        this.delay = b.delay;
        this.ttl = b.ttl;
        this.tags = b.tags == null ? List.of() : List.copyOf(b.tags);
    }

    public static Builder builder() {
        return new Builder();
    }

    public static final class Builder {
        private Priority priority = Priority.NORMAL;
        private String key;
        private Long delay;
        private Long ttl;
        private List<String> tags;

        public Builder priority(Priority priority) {
            this.priority = priority;
            return this;
        }

        public Builder key(String key) {
            this.key = key;
            return this;
        }

        public Builder delay(long seconds) {
            this.delay = seconds;
            return this;
        }

        public Builder ttl(long seconds) {
            this.ttl = seconds;
            return this;
        }

        public Builder tags(List<String> tags) {
            this.tags = tags;
            return this;
        }

        public SendOptions build() {
            return new SendOptions(this);
        }
    }
}
