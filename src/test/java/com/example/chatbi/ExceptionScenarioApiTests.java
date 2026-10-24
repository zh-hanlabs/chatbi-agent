package com.example.chatbi;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
@ActiveProfiles("test")
class ExceptionScenarioApiTests {

    @Autowired
    private MockMvc mockMvc;

    @Test
    void malformedJsonIsBadRequest() throws Exception {
        mockMvc.perform(post("/api/conversations")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"userId\": "))
                .andExpect(status().isBadRequest());
    }

    @Test
    void wrongFieldTypeIsBadRequest() throws Exception {
        mockMvc.perform(post("/api/conversations")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"userId\":\"abc\",\"title\":\"x\"}"))
                .andExpect(status().isBadRequest());
    }

    @Test
    void unsupportedMediaTypeIsRejected() throws Exception {
        mockMvc.perform(post("/api/nl2sql")
                        .contentType(MediaType.TEXT_PLAIN)
                        .content("{\"question\":\"GMV\"}"))
                .andExpect(status().isUnsupportedMediaType());
    }

    @Test
    void guardPassingButInvalidSqlIs422Not500() throws Exception {
        // 通过安全校验(单条 SELECT、白名单表)但列不存在 → 客户端错误,不该 500
        mockMvc.perform(post("/api/sql/confirm")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"userId\":1,\"sql\":\"SELECT nonexistent_column FROM orders\"}"))
                .andExpect(status().isUnprocessableEntity())
                .andExpect(jsonPath("$.error").value("SQL 执行失败: 语法错误或引用了不存在的表/列"));
    }

    @Test
    void missingResourceReturns404AcrossEndpoints() throws Exception {
        mockMvc.perform(get("/api/conversations/not-exist/context").param("userId", "1"))
                .andExpect(status().isNotFound());
        mockMvc.perform(get("/api/documents/999"))
                .andExpect(status().isNotFound());
        mockMvc.perform(get("/api/conversations/not-exist/messages").param("userId", "1"))
                .andExpect(status().isNotFound());
    }

    @Test
    void methodNotAllowedIsRejected() throws Exception {
        mockMvc.perform(get("/api/sql/confirm"))
                .andExpect(status().isMethodNotAllowed());
    }
}
