package com.example.chatbi.agent;

import java.util.List;

public interface AgentClient {
    AgentResult complete(List<ToolCall> requestedTools);
}
