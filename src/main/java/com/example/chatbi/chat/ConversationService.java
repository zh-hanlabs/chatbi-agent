package com.example.chatbi.chat;

import com.example.chatbi.agent.ToolCall;
import com.example.chatbi.api.NotFoundException;
import com.example.chatbi.api.PermissionDeniedException;
import com.example.chatbi.audit.AuditService;
import com.example.chatbi.rag.RagRouter;
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.List;
import java.util.Map;
import java.util.UUID;

@Service
public class ConversationService {

    public record ChatReply(String answer, ToolCall toolCall, boolean requiresTool,
                            long userMessageId, long assistantMessageId) {
    }

    private final ConversationRepository repository;
    private final RagRouter ragRouter;
    private final ObjectMapper objectMapper;
    private final AuditService auditService;
    private final ContextCompressor contextCompressor;

    public ConversationService(ConversationRepository repository, RagRouter ragRouter, ObjectMapper objectMapper,
            AuditService auditService, ContextCompressor contextCompressor) {
        this.repository = repository;
        this.ragRouter = ragRouter;
        this.objectMapper = objectMapper;
        this.auditService = auditService;
        this.contextCompressor = contextCompressor;
    }

    @Transactional
    public Conversation createConversation(long userId, String title) {
        requireUser(userId);
        Conversation conversation = new Conversation(UUID.randomUUID().toString(), userId, title, null, null);
        repository.insert(conversation);
        return repository.findById(conversation.id()).orElseThrow();
    }

    public List<Conversation> listConversations(long userId) {
        requireUser(userId);
        return repository.findByUserId(userId);
    }

    public List<ChatMessage> listMessages(String conversationId, long userId) {
        Conversation conversation = requireOwnedConversation(conversationId, userId);
        return repository.findMessages(conversation.id());
    }

    @Transactional
    public ChatReply chat(String conversationId, long userId, String question) {
        Conversation conversation = requireOwnedConversation(conversationId, userId);

        long userMessageId = repository.insertMessage(
                new ChatMessage(null, conversation.id(), "USER", question, null, null));

        RagRouter.RoutedAnswer routed;
        try {
            routed = ragRouter.route(conversation.userId(), question);
        } catch (PermissionDeniedException e) {
            auditService.record(conversation.userId(), conversation.id(), AuditService.ACTION_CHAT, question,
                    null, false, "PERMISSION_DENIED: " + e.getMessage());
            throw e;
        }
        boolean requiresTool = RagRouter.ROUTE_NL2SQL.equals(routed.route()) && routed.sql() != null;
        ToolCall toolCall = requiresTool
                ? new ToolCall(UUID.randomUUID().toString(), "execute_sql", Map.of("sql", routed.sql().sql()))
                : null;
        String answer = requiresTool
                ? "已生成查询 SQL,确认后执行: " + routed.sql().sql()
                : routed.answer();
        String toolCallJson = serializeToolCall(toolCall);
        long assistantMessageId = repository.insertMessage(
                new ChatMessage(null, conversation.id(), "ASSISTANT", answer, toolCallJson, null));

        repository.touchUpdatedAt(conversation.id());
        auditService.record(conversation.userId(), conversation.id(), AuditService.ACTION_CHAT, question,
                routed.sql() == null ? null : routed.sql().sql(), true, "route=" + routed.route());
        return new ChatReply(answer, toolCall, requiresTool, userMessageId, assistantMessageId);
    }

    public ContextCompressor.CompressedContext buildContext(String conversationId, long userId) {
        Conversation conversation = requireOwnedConversation(conversationId, userId);
        return contextCompressor.compress(repository.findMessages(conversation.id()));
    }

    private void requireUser(long userId) {
        if (!repository.userExists(userId)) {
            throw new NotFoundException("用户不存在: " + userId);
        }
    }

    private Conversation requireOwnedConversation(String conversationId, long userId) {
        Conversation conversation = repository.findById(conversationId)
                .orElseThrow(() -> new NotFoundException("对话不存在: " + conversationId));
        if (conversation.userId() != userId) {
            // 非本人对话一律按不存在处理，避免泄露其他用户的对话
            throw new NotFoundException("对话不存在: " + conversationId);
        }
        return conversation;
    }

    private String serializeToolCall(ToolCall toolCall) {
        if (toolCall == null) {
            return null;
        }
        try {
            return objectMapper.writeValueAsString(toolCall);
        } catch (JsonProcessingException e) {
            throw new IllegalStateException("工具调用序列化失败", e);
        }
    }
}
