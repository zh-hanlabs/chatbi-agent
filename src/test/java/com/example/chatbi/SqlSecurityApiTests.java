package com.example.chatbi;

import com.example.chatbi.nl2sql.GeneratedSql;
import com.example.chatbi.nl2sql.SqlGenerator;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.web.servlet.MockMvc;

import java.util.List;

import static org.hamcrest.Matchers.closeTo;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
@ActiveProfiles("test")
class SqlSecurityApiTests {

    @Autowired
    private MockMvc mockMvc;

    @Autowired
    private SqlGenerator sqlGenerator;

    @Test
    void validateAllowsAllGeneratedSql() throws Exception {
        List<String> questions = List.of("北京的 GMV", "上海的订单量", "广州的退款率", "近7天的 GMV", "总订单量");
        for (String question : questions) {
            GeneratedSql generated = sqlGenerator.generate(question);
            mockMvc.perform(post("/api/sql/validate")
                            .contentType(MediaType.APPLICATION_JSON)
                            .content("{\"sql\":%s}".formatted(jsonEscape(generated.sql()))))
                    .andExpect(status().isOk())
                    .andExpect(jsonPath("$.allowed").value(true))
                    .andExpect(jsonPath("$.reason").doesNotExist());
        }
    }

    @Test
    void validateRejectsWriteStatements() throws Exception {
        for (String sql : List.of(
                "UPDATE orders SET amount = 0",
                "DELETE FROM orders",
                "DROP TABLE orders",
                "INSERT INTO regions(id, name) VALUES (9, 'x')",
                "TRUNCATE TABLE orders",
                "SELECT amount FROM orders FOR UPDATE")) {
            mockMvc.perform(post("/api/sql/validate")
                            .contentType(MediaType.APPLICATION_JSON)
                            .content("{\"sql\":%s}".formatted(jsonEscape(sql))))
                    .andExpect(status().isOk())
                    .andExpect(jsonPath("$.allowed").value(false))
                    .andExpect(jsonPath("$.reason").isNotEmpty());
        }
    }

    @Test
    void validateRejectsStackedStatementsAndComments() throws Exception {
        for (String sql : List.of(
                "SELECT 1; DROP TABLE orders",
                "SELECT amount FROM orders -- AND 1=1",
                "SELECT amount FROM orders /* comment */ WHERE 1=1",
                "SELECT amount FROM orders# comment")) {
            mockMvc.perform(post("/api/sql/validate")
                            .contentType(MediaType.APPLICATION_JSON)
                            .content("{\"sql\":%s}".formatted(jsonEscape(sql))))
                    .andExpect(status().isOk())
                    .andExpect(jsonPath("$.allowed").value(false));
        }
    }

    @Test
    void validateRejectsTableWhitelistBypass() throws Exception {
        for (String sql : List.of(
                "SELECT username FROM users",
                "SELECT amount FROM `users`",
                "SELECT username FROM \"users\"",
                "SELECT table_name FROM information_schema.tables")) {
            mockMvc.perform(post("/api/sql/validate")
                            .contentType(MediaType.APPLICATION_JSON)
                            .content("{\"sql\":%s}".formatted(jsonEscape(sql))))
                    .andExpect(status().isOk())
                    .andExpect(jsonPath("$.allowed").value(false));
        }
    }

    @Test
    void validateRejectsSensitiveColumnAndWildcard() throws Exception {
        for (String sql : List.of(
                "SELECT customer_phone FROM orders",
                "SELECT id, customer_phone FROM orders WHERE amount > 100",
                "SELECT * FROM orders",
                "SELECT o.* FROM orders o",
                "SELECT amount, * FROM orders")) {
            mockMvc.perform(post("/api/sql/validate")
                            .contentType(MediaType.APPLICATION_JSON)
                            .content("{\"sql\":%s}".formatted(jsonEscape(sql))))
                    .andExpect(status().isOk())
                    .andExpect(jsonPath("$.allowed").value(false));
        }
    }

    @Test
    void validateRejectsDangerousFunctionsAndOutfile() throws Exception {
        for (String sql : List.of(
                "SELECT benchmark(100000000, md5('x'))",
                "SELECT sleep(10)",
                "SELECT amount FROM orders INTO OUTFILE '/tmp/leak'")) {
            mockMvc.perform(post("/api/sql/validate")
                            .contentType(MediaType.APPLICATION_JSON)
                            .content("{\"sql\":%s}".formatted(jsonEscape(sql))))
                    .andExpect(status().isOk())
                    .andExpect(jsonPath("$.allowed").value(false));
        }
    }

    @Test
    void stringLiteralsDoNotTriggerFalsePositives() throws Exception {
        mockMvc.perform(post("/api/sql/validate")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"sql\":\"SELECT COUNT(*) AS c FROM regions WHERE name = 'update; drop table'\"}"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.allowed").value(true));
    }

    @Test
    void confirmExecutesGeneratedGmvSql() throws Exception {
        GeneratedSql generated = sqlGenerator.generate("北京的 GMV");
        mockMvc.perform(post("/api/sql/confirm")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"sql\":%s}".formatted(jsonEscape(generated.sql()))))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.rowCount").value(1))
                .andExpect(jsonPath("$.columns[0]").value("gmv"))
                .andExpect(jsonPath("$.rows[0].gmv", closeTo(1098.0, 0.001)))
                .andExpect(jsonPath("$.truncated").value(false));
    }

    @Test
    void confirmExecutesAggregateWithoutRegion() throws Exception {
        GeneratedSql generated = sqlGenerator.generate("总订单量");
        mockMvc.perform(post("/api/sql/confirm")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"sql\":%s}".formatted(jsonEscape(generated.sql()))))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.rows[0].order_count").value(5));
    }

    @Test
    void confirmRejectsUnsafeSqlWith422() throws Exception {
        mockMvc.perform(post("/api/sql/confirm")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"sql\":\"UPDATE orders SET amount = 0\"}"))
                .andExpect(status().isUnprocessableEntity())
                .andExpect(jsonPath("$.error").isNotEmpty());
    }

    @Test
    void blankSqlIsRejected() throws Exception {
        mockMvc.perform(post("/api/sql/confirm")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"sql\":\" \"}"))
                .andExpect(status().isBadRequest());
    }

    private String jsonEscape(String value) {
        try {
            return new com.fasterxml.jackson.databind.ObjectMapper().writeValueAsString(value);
        } catch (Exception e) {
            throw new IllegalStateException(e);
        }
    }
}
