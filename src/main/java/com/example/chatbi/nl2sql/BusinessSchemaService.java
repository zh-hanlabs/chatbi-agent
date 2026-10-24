package com.example.chatbi.nl2sql;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;

import java.util.Comparator;
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

/**
 * 检索业务表结构，供 NL2SQL 提示词与调试接口使用。
 * 只暴露白名单内的业务表，系统表（用户/会话/审计）一律不外泄。
 */
@Service
public class BusinessSchemaService {

    private static final List<String> BUSINESS_TABLES = List.of("orders", "products", "regions");

    private final JdbcTemplate jdbcTemplate;

    public BusinessSchemaService(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }

    public List<TableSchema> businessTables() {
        record RawColumn(String table, String name, String type) {
        }

        String placeholders = BUSINESS_TABLES.stream().map(t -> "?").collect(Collectors.joining(","));
        List<RawColumn> columns = jdbcTemplate.query(
                "SELECT table_name, column_name, data_type FROM information_schema.columns "
                        + "WHERE table_name IN (" + placeholders + ")",
                (rs, rowNum) -> new RawColumn(rs.getString(1), rs.getString(2), rs.getString(3)),
                BUSINESS_TABLES.toArray());

        Map<String, List<TableSchema.ColumnSchema>> byTable = columns.stream()
                .collect(Collectors.groupingBy(RawColumn::table,
                        Collectors.mapping(col -> new TableSchema.ColumnSchema(col.name(), col.type()),
                                Collectors.toList())));

        return BUSINESS_TABLES.stream()
                .filter(byTable::containsKey)
                .map(table -> new TableSchema(table,
                        byTable.get(table).stream()
                                .sorted(Comparator.comparing(TableSchema.ColumnSchema::name))
                                .toList()))
                .toList();
    }
}
