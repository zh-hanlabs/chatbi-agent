package com.example.chatbi.chat;

import java.time.LocalDateTime;

public record Conversation(String id, long userId, String title, LocalDateTime createdAt, LocalDateTime updatedAt) {
}
