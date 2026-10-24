package com.example.chatbi;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.web.servlet.MockMvc;

import static org.hamcrest.Matchers.greaterThanOrEqualTo;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
@ActiveProfiles("test")
class EvaluationApiTests {

    @Autowired
    private MockMvc mockMvc;

    @Autowired
    private JdbcTemplate jdbcTemplate;

    @BeforeEach
    void cleanKnowledgeBase() {
        jdbcTemplate.update("DELETE FROM document_chunks");
        jdbcTemplate.update("DELETE FROM documents");
    }

    @Test
    void evaluationSuiteHasAtLeastFiftyCases() {
        Integer cases = jdbcTemplate.queryForObject("SELECT COUNT(*) FROM evaluation_cases", Integer.class);
        org.assertj.core.api.Assertions.assertThat(cases).isGreaterThanOrEqualTo(50);
    }

    @Test
    void evaluationRunMeetsAccuracyBar() throws Exception {
        mockMvc.perform(get("/api/evaluations"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.total", greaterThanOrEqualTo(50)))
                .andExpect(jsonPath("$.accuracy", greaterThanOrEqualTo(0.95)))
                .andExpect(jsonPath("$.byCategory.NL2SQL.accuracy", greaterThanOrEqualTo(0.95)))
                .andExpect(jsonPath("$.byCategory.RAG.accuracy", greaterThanOrEqualTo(0.9)))
                .andExpect(jsonPath("$.byCategory.REFUSAL.accuracy", greaterThanOrEqualTo(0.9)))
                .andExpect(jsonPath("$.byCategory.SQL_GUARD.accuracy", greaterThanOrEqualTo(0.99)));
    }

    @Test
    void evaluationReportListsFailuresWithActual() throws Exception {
        mockMvc.perform(get("/api/evaluations"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.failures").isArray())
                .andExpect(jsonPath("$.byCategory.NL2SQL.total", greaterThanOrEqualTo(20)))
                .andExpect(jsonPath("$.byCategory.RAG.total", greaterThanOrEqualTo(15)))
                .andExpect(jsonPath("$.byCategory.REFUSAL.total", greaterThanOrEqualTo(10)))
                .andExpect(jsonPath("$.byCategory.SQL_GUARD.total", greaterThanOrEqualTo(5)));
    }
}
