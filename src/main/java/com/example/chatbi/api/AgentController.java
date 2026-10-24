package com.example.chatbi.api;

import com.example.chatbi.agent.AgentClient;
import com.example.chatbi.agent.AgentResult;
import com.example.chatbi.agent.MockAgentClient;
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;

@RestController
@RequestMapping("/api")
public class AgentController {
    private final AgentClient agentClient = new MockAgentClient();

    public record ChatRequest(@NotBlank String question) {
    }

    @PostMapping("/chat")
    public ResponseEntity<AgentResult> chat(@Valid @RequestBody ChatRequest request) {
        return ResponseEntity.ok(agentClient.complete(List.of()));
    }

    @GetMapping("/tools")
    public ResponseEntity<AgentResult> requestTool() {
        MockAgentClient client = (MockAgentClient) agentClient;
        return ResponseEntity.ok(client.complete(List.of(client.requestGmvTool())));
    }
}
