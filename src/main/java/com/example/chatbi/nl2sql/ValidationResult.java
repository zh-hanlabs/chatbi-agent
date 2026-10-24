package com.example.chatbi.nl2sql;

public record ValidationResult(boolean allowed, String reason) {

    public static ValidationResult ok() {
        return new ValidationResult(true, null);
    }

    public static ValidationResult rejected(String reason) {
        return new ValidationResult(false, reason);
    }
}
