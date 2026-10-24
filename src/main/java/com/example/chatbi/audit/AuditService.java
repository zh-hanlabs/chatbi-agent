package com.example.chatbi.audit;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.RowMapper;
import org.springframework.stereotype.Service;

import java.sql.Timestamp;
import java.util.List;

/**
 * 审计日志:记录每次问数/SQL 执行尝试(含被拒绝的),供管理端追溯与演示安全边界。
 */
@Service
public class AuditService {

    public static final String ACTION_CHAT = "CHAT";
    public static final String ACTION_SQL_CONFIRM = "SQL_CONFIRM";

    public record AuditEntry(Long id, Long userId, String conversationId, String action, String question,
                             String generatedSql, boolean allowed, String reason,
                             Timestamp createdAt) {
    }

    private static final RowMapper<AuditEntry> ROW = (rs, rowNum) -> new AuditEntry(
            rs.getLong("id"),
            rs.getLong("user_id"),
            rs.getString("conversation_id"),
            rs.getString("action"),
            rs.getString("question"),
            rs.getString("generated_sql"),
            rs.getBoolean("allowed"),
            rs.getString("reason"),
            rs.getTimestamp("created_at"));

    private final JdbcTemplate jdbcTemplate;

    public AuditService(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }

    public void record(long userId, String conversationId, String action, String question, String generatedSql,
                       boolean allowed, String reason) {
        jdbcTemplate.update(
                "INSERT INTO audit_logs(user_id, conversation_id, action, question, generated_sql, allowed, reason) "
                        + "VALUES (?, ?, ?, ?, ?, ?, ?)",
                userId, conversationId, action, question, generatedSql, allowed, reason);
    }

    public List<AuditEntry> listRecent(int limit) {
        return jdbcTemplate.query(
                "SELECT id, user_id, conversation_id, action, question, generated_sql, allowed, reason, created_at "
                        + "FROM audit_logs ORDER BY id DESC LIMIT " + Math.min(Math.max(limit, 1), 200),
                ROW);
    }

    public boolean isAdmin(long userId) {
        String role = jdbcTemplate.queryForObject("SELECT role FROM users WHERE id = ?", String.class, userId);
        return "ADMIN".equals(role);
    }
}
