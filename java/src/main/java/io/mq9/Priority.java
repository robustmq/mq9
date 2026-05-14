package io.mq9;

/**
 * Message priority levels for mq9.
 */
public enum Priority {
    NORMAL("normal"),
    URGENT("urgent"),
    CRITICAL("critical");

    public final String value;

    Priority(String value) {
        this.value = value;
    }

    /**
     * Parse a priority from its wire string value. Defaults to NORMAL if unknown.
     */
    public static Priority fromValue(String value) {
        if (value == null) return NORMAL;
        return switch (value.toLowerCase()) {
            case "urgent" -> URGENT;
            case "critical" -> CRITICAL;
            default -> NORMAL;
        };
    }
}
