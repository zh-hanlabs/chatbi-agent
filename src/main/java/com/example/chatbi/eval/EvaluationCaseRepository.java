package com.example.chatbi.eval;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.RowMapper;
import org.springframework.stereotype.Repository;

import java.util.List;

@Repository
public class EvaluationCaseRepository {

    public record EvalCase(long id, String category, String question, String expectedRoute, String expectedMetric,
                           String expectedSql, String expectedAnswerContains, Boolean expectedAllowed) {
    }

    private static final RowMapper<EvalCase> ROW = (rs, rowNum) -> new EvalCase(
            rs.getLong("id"),
            rs.getString("category"),
            rs.getString("question"),
            rs.getString("expected_route"),
            rs.getString("expected_metric"),
            rs.getString("expected_sql"),
            rs.getString("expected_answer_contains"),
            rs.getObject("expected_allowed", Boolean.class));

    private final JdbcTemplate jdbcTemplate;

    public EvaluationCaseRepository(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }

    public List<EvalCase> findAll() {
        return jdbcTemplate.query(
                "SELECT id, category, question, expected_route, expected_metric, expected_sql, "
                        + "expected_answer_contains, expected_allowed FROM evaluation_cases ORDER BY id",
                ROW);
    }
}
