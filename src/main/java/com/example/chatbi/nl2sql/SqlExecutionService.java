package com.example.chatbi.nl2sql;

import com.example.chatbi.api.SqlNotAllowedException;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;

import javax.sql.DataSource;
import java.util.List;
import java.util.Map;

/**
 * 执行前确认:服务端重新校验 SQL(不信任客户端已校验),通过后以限流参数执行。
 * 行数上限与查询超时在 JdbcTemplate 层兜底,防止大结果集与变相 DoS。
 */
@Service
public class SqlExecutionService {

    public static final int MAX_ROWS = 100;
    private static final int QUERY_TIMEOUT_SECONDS = 5;

    public record SqlExecutionResult(List<String> columns, List<Map<String, Object>> rows, int rowCount,
                                     boolean truncated) {
    }

    private final SqlSecurityValidator validator;
    private final JdbcTemplate jdbcTemplate;

    public SqlExecutionService(SqlSecurityValidator validator, DataSource dataSource) {
        this.validator = validator;
        JdbcTemplate template = new JdbcTemplate(dataSource);
        template.setMaxRows(MAX_ROWS);
        template.setQueryTimeout(QUERY_TIMEOUT_SECONDS);
        this.jdbcTemplate = template;
    }

    public SqlExecutionResult confirmAndExecute(String sql) {
        ValidationResult verdict = validator.validate(sql);
        if (!verdict.allowed()) {
            throw new SqlNotAllowedException(verdict.reason());
        }
        List<Map<String, Object>> rows = jdbcTemplate.queryForList(sql);
        List<String> columns = rows.isEmpty() ? List.of() : List.copyOf(rows.getFirst().keySet());
        boolean truncated = rows.size() == MAX_ROWS;
        return new SqlExecutionResult(columns, rows, rows.size(), truncated);
    }
}
