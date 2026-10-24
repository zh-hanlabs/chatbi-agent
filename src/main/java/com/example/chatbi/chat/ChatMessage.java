package com.example.chatbi.chat;

import java.time.LocalDateTime;

public record ChatMessage(Long id, String conversationId, String role, String content, String toolCallJson,
                          LocalDateTime createdAt) {
}
