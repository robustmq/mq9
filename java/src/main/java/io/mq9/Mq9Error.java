package io.mq9;

/**
 * Thrown when the mq9 broker returns a non-empty error field, or when a
 * transport-level failure occurs.
 */
public class Mq9Error extends RuntimeException {

    public Mq9Error(String message) {
        super(message);
    }

    public Mq9Error(String message, Throwable cause) {
        super(message, cause);
    }
}
