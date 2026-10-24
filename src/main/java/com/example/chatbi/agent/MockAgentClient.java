package com.example.chatbi.agent;

import java.util.List;
import java.util.Map;
import java.util.UUID;

public class MockAgentClient implements AgentClient {
    @Override
    public AgentResult complete(List<ToolCall> requestedTools) {
        if (!requestedTools.isEmpty()) {
            ToolCall tool = requestedTools.getFirst();
            return new AgentResult("Tool execution requested", tool, true);
        }
        return new AgentResult("GMV is the sum of completed order amounts.", null, false);
    }

    public ToolCall requestGmvTool() {
        return new ToolCall(UUID.randomUUID().toString(), "query_gmv", Map.of("metric", "gmv"));
    }
}
