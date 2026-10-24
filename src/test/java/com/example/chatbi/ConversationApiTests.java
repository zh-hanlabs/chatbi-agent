package com.example.chatbi;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
@ActiveProfiles("test")
class ConversationApiTests {

    @Autowired
    private MockMvc mockMvc;

    @Autowired
    private JdbcTemplate jdbcTemplate;

    @BeforeEach
    void cleanConversations() {
        jdbcTemplate.update("DELETE FROM messages");
        jdbcTemplate.update("DELETE FROM conversations");
    }

    @Test
    void createConversationPersistsAndReturnsIt() throws Exception {
        mockMvc.perform(post("/api/conversations")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"userId\":1,\"title\":\"北京经营分析\"}"))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.id").isNotEmpty())
                .andExpect(jsonPath("$.userId").value(1))
                .andExpect(jsonPath("$.title").value("北京经营分析"))
                .andExpect(jsonPath("$.createdAt").isNotEmpty());
    }

    @Test
    void listConversationsOnlyReturnsOwnOnes() throws Exception {
        String bjConversationId = createConversation(1, "北京会话");
        createConversation(2, "上海会话");

        mockMvc.perform(get("/api/conversations").param("userId", "1"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.length()").value(1))
                .andExpect(jsonPath("$[0].id").value(bjConversationId));
    }

    @Test
    void chatPersistsUserAndAssistantMessages() throws Exception {
        String conversationId = createConversation(1, "口径问答");

        mockMvc.perform(post("/api/conversations/{id}/chat", conversationId)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"userId\":1,\"question\":\"GMV 的口径是什么\"}"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.answer").isNotEmpty())
                .andExpect(jsonPath("$.userMessageId").isNumber())
                .andExpect(jsonPath("$.assistantMessageId").isNumber());

        mockMvc.perform(get("/api/conversations/{id}/messages", conversationId).param("userId", "1"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.length()").value(2))
                .andExpect(jsonPath("$[0].role").value("USER"))
                .andExpect(jsonPath("$[0].content").value("GMV 的口径是什么"))
                .andExpect(jsonPath("$[1].role").value("ASSISTANT"))
                .andExpect(jsonPath("$[1].content").isNotEmpty());
    }

    @Test
    void chatOnForeignConversationIsNotFound() throws Exception {
        String conversationId = createConversation(1, "北京私有会话");

        mockMvc.perform(post("/api/conversations/{id}/chat", conversationId)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"userId\":2,\"question\":\"看看别人的对话\"}"))
                .andExpect(status().isNotFound());

        mockMvc.perform(get("/api/conversations/{id}/messages", conversationId).param("userId", "2"))
                .andExpect(status().isNotFound());
    }

    @Test
    void blankQuestionIsRejected() throws Exception {
        String conversationId = createConversation(1, "校验会话");

        mockMvc.perform(post("/api/conversations/{id}/chat", conversationId)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"userId\":1,\"question\":\" \"}"))
                .andExpect(status().isBadRequest());
    }

    @Test
    void unknownUserIsRejected() throws Exception {
        mockMvc.perform(post("/api/conversations")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"userId\":999,\"title\":\"不存在的用户\"}"))
                .andExpect(status().isNotFound());
    }

    private String createConversation(long userId, String title) throws Exception {
        MvcResult result = mockMvc.perform(post("/api/conversations")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"userId\":%d,\"title\":\"%s\"}".formatted(userId, title)))
                .andExpect(status().isCreated())
                .andReturn();
        return new ObjectMapper().readTree(result.getResponse().getContentAsString()).get("id").asText();
    }
}
