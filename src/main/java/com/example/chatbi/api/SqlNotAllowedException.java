package com.example.chatbi.api;

public class SqlNotAllowedException extends RuntimeException {
    public SqlNotAllowedException(String reason) {
        super(reason);
    }
}
