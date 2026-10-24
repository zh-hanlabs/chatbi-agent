package com.example.chatbi.api;

import com.example.chatbi.chat.ChatMessage;
import com.example.chatbi.chat.ContextCompressor;
import com.example.chatbi.chat.Conversation;
import com.example.chatbi.chat.ConversationService;
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;

@RestController
@RequestMapping("/api/conversations")
public class ConversationController {

    private final ConversationService conversationService;

    public ConversationController(ConversationService conversationService) {
        this.conversationService = conversationService;
    }

    public record CreateConversationRequest(@NotNull Long userId, @NotBlank String title) {
    }

    public record ConversationChatRequest(@NotNull Long userId, @NotBlank String question) {
    }

    @PostMapping
    public ResponseEntity<Conversation> create(@Valid @RequestBody CreateConversationRequest request) {
        Conversation conversation = conversationService.createConversation(request.userId(), request.title());
        return ResponseEntity.status(201).body(conversation);
    }

    @GetMapping
    public ResponseEntity<List<Conversation>> list(@RequestParam long userId) {
        return ResponseEntity.ok(conversationService.listConversations(userId));
    }

    @GetMapping("/{id}/messages")
    public ResponseEntity<List<ChatMessage>> messages(@PathVariable String id, @RequestParam long userId) {
        return ResponseEntity.ok(conversationService.listMessages(id, userId));
    }

    /** 多轮上下文压缩视图:超出阈值的历史折叠为摘要,只保留最近几轮原文 */
    @GetMapping("/{id}/context")
    public ResponseEntity<ContextCompressor.CompressedContext> context(@PathVariable String id,
            @RequestParam long userId) {
        return ResponseEntity.ok(conversationService.buildContext(id, userId));
    }

    @PostMapping("/{id}/chat")
    public ResponseEntity<ConversationService.ChatReply> chat(@PathVariable String id,
            @Valid @RequestBody ConversationChatRequest request) {
        return ResponseEntity.ok(conversationService.chat(id, request.userId(), request.question()));
    }
}
