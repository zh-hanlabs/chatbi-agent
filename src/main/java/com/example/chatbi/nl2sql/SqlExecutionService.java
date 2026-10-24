package com.example.chatbi.nl2sql;

import com.example.chatbi.api.SqlNotAllowedException;
import com.example.chatbi.audit.AuditService;
import com.example.chatbi.cache.ChatCache;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;

import javax.sql.DataSource;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.time.Duration;
import java.util.HexFormat;
import java.util.List;
import java.util.Map;
import java.util.Optional;

/**
 * 执行前确认:服务端重新校验 SQL(不信任客户端已校验),通过后以限流参数执行。
 * 行数上限与查询超时在 JdbcTemplate 层兜底,防止大结果集与变相 DoS;
 * 高频相同查询走缓存,每次尝试(含拒绝与缓存命中)均落审计。
 */
@Service
public class SqlExecutionService {

    public static final int MAX_ROWS = 100;
    private static final int QUERY_TIMEOUT_SECONDS = 5;

    /** 缓存命中的结果单独反序列化,避免把 cacheHit 标志写进缓存内容 */
    public record CachedResult(List<String> columns, List<Map<String, Object>> rows, int rowCount,
                               boolean truncated) {
    }

    public record SqlExecutionResult(List<String> columns, List<Map<String, Object>> rows, int rowCount,
                                     boolean truncated, boolean cacheHit) {
    }

    private final SqlSecurityValidator validator;
    private final JdbcTemplate jdbcTemplate;
    private final ChatCache chatCache;
    private final AuditService auditService;
    private final ObjectMapper objectMapper;
    private final long cacheTtlSeconds;

    public SqlExecutionService(SqlSecurityValidator validator, DataSource dataSource, ChatCache chatCache,
            AuditService auditService, ObjectMapper objectMapper,
            @Value("${chatbi.cache.ttl-seconds:300}") long cacheTtlSeconds) {
        this.validator = validator;
        JdbcTemplate template = new JdbcTemplate(dataSource);
        template.setMaxRows(MAX_ROWS);
        template.setQueryTimeout(QUERY_TIMEOUT_SECONDS);
        this.jdbcTemplate = template;
        this.chatCache = chatCache;
        this.auditService = auditService;
        this.objectMapper = objectMapper;
        this.cacheTtlSeconds = cacheTtlSeconds;
    }

    public SqlExecutionResult confirmAndExecute(long userId, String conversationId, String sql) {
        String cacheKey = "sql-result:" + userId + ":" + sha256(sql);
        Optional<SqlExecutionResult> cached = readCache(cacheKey);
        if (cached.isPresent()) {
            auditService.record(userId, conversationId, AuditService.ACTION_SQL_CONFIRM, sql, sql, true, "cache_hit");
            return cached.get();
        }

        ValidationResult verdict = validator.validate(sql);
        if (!verdict.allowed()) {
            auditService.record(userId, conversationId, AuditService.ACTION_SQL_CONFIRM, sql, sql, false,
                    verdict.reason());
            throw new SqlNotAllowedException(verdict.reason());
        }

        List<Map<String, Object>> rows = jdbcTemplate.queryForList(sql);
        List<String> columns = rows.isEmpty() ? List.of() : List.copyOf(rows.getFirst().keySet());
        boolean truncated = rows.size() == MAX_ROWS;
        SqlExecutionResult result = new SqlExecutionResult(columns, rows, rows.size(), truncated, false);
        writeCache(cacheKey, result);
        auditService.record(userId, conversationId, AuditService.ACTION_SQL_CONFIRM, sql, sql, true, "executed");
        return result;
    }

    private Optional<SqlExecutionResult> readCache(String cacheKey) {
        return chatCache.get(cacheKey).map(json -> {
            try {
                CachedResult cached = objectMapper.readValue(json, CachedResult.class);
                return new SqlExecutionResult(cached.columns(), cached.rows(), cached.rowCount(), cached.truncated(),
                        true);
            } catch (Exception e) {
                return null;
            }
        });
    }

    private void writeCache(String cacheKey, SqlExecutionResult result) {
        try {
            String json = objectMapper.writeValueAsString(
                    new CachedResult(result.columns(), result.rows(), result.rowCount(), result.truncated()));
            chatCache.put(cacheKey, json, Duration.ofSeconds(cacheTtlSeconds));
        } catch (Exception ignored) {
            // 缓存写入失败不影响主链路
        }
    }

    private String sha256(String value) {
        try {
            MessageDigest digest = MessageDigest.getInstance("SHA-256");
            return HexFormat.of().formatHex(digest.digest(value.getBytes(StandardCharsets.UTF_8)));
        } catch (NoSuchAlgorithmException e) {
            throw new IllegalStateException("SHA-256 不可用", e);
        }
    }
}
