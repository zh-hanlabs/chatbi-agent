package com.example.chatbi.agent;

public record AgentResult(String answer, ToolCall toolCall, boolean requiresTool) {
}
