package com.example.chatbi.agent;

import java.util.Map;

public record ToolCall(String id, String name, Map<String, Object> arguments) {
}
