package com.example.chatbi.chat;

import com.example.chatbi.agent.AgentClient;
import com.example.chatbi.agent.AgentResult;
import com.example.chatbi.agent.ToolCall;
import com.example.chatbi.api.NotFoundException;
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.List;
import java.util.UUID;

@Service
public class ConversationService {

    public record ChatReply(String answer, ToolCall toolCall, boolean requiresTool,
                            long userMessageId, long assistantMessageId) {
    }

    private final ConversationRepository repository;
    private final AgentClient agentClient;
    private final ObjectMapper objectMapper;

    public ConversationService(ConversationRepository repository, AgentClient agentClient, ObjectMapper objectMapper) {
        this.repository = repository;
        this.agentClient = agentClient;
        this.objectMapper = objectMapper;
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

        AgentResult result = agentClient.complete(List.of());
        String toolCallJson = serializeToolCall(result);
        long assistantMessageId = repository.insertMessage(
                new ChatMessage(null, conversation.id(), "ASSISTANT", result.answer(), toolCallJson, null));

        repository.touchUpdatedAt(conversation.id());
        return new ChatReply(result.answer(), result.toolCall(), result.requiresTool(),
                userMessageId, assistantMessageId);
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

    private String serializeToolCall(AgentResult result) {
        if (!result.requiresTool() || result.toolCall() == null) {
            return null;
        }
        try {
            return objectMapper.writeValueAsString(result.toolCall());
        } catch (JsonProcessingException e) {
            throw new IllegalStateException("工具调用序列化失败", e);
        }
    }
}
