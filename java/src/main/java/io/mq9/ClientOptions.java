package io.mq9;

import java.time.Duration;

/**
 * Connection-level options for {@link Mq9Client}.
 */
public final class ClientOptions {

    /** Timeout applied to every NATS request/reply round-trip. Default 5 s. */
    public final Duration requestTimeout;

    private ClientOptions(Builder b) {
        this.requestTimeout = b.requestTimeout;
    }

    public static Builder builder() {
        return new Builder();
    }

    public static final class Builder {
        private Duration requestTimeout = Duration.ofSeconds(5);

        public Builder requestTimeout(Duration requestTimeout) {
            this.requestTimeout = requestTimeout;
            return this;
        }

        public ClientOptions build() {
            return new ClientOptions(this);
        }
    }
}
