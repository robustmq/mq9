package io.mq9;

import java.util.Map;

/**
 * A message received from a mq9 mailbox.
 */
public final class Message {

    public final long msgId;
    public final byte[] payload;
    public final Priority priority;
    /** Unix timestamp in seconds when the message was created on the broker. */
    public final long createTime;
    /** Protocol headers attached to the message; may be {@code null}. */
    public final Map<String, String> headers;

    public Message(long msgId, byte[] payload, Priority priority, long createTime) {
        this(msgId, payload, priority, createTime, null);
    }

    public Message(long msgId, byte[] payload, Priority priority, long createTime,
                   Map<String, String> headers) {
        this.msgId = msgId;
        this.payload = payload;
        this.priority = priority;
        this.createTime = createTime;
        this.headers = headers;
    }

    @Override
    public String toString() {
        return "Message{msgId=" + msgId
                + ", priority=" + priority
                + ", createTime=" + createTime
                + ", payloadBytes=" + (payload == null ? 0 : payload.length)
                + '}';
    }
}
