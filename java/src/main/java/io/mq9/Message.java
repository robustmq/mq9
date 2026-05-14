package io.mq9;

/**
 * A message received from a mq9 mailbox.
 */
public final class Message {

    public final long msgId;
    public final byte[] payload;
    public final Priority priority;
    /** Unix timestamp in seconds when the message was created on the broker. */
    public final long createTime;

    public Message(long msgId, byte[] payload, Priority priority, long createTime) {
        this.msgId = msgId;
        this.payload = payload;
        this.priority = priority;
        this.createTime = createTime;
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
