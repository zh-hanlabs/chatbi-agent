package com.example.chatbi.nl2sql;

import java.util.List;

public record TableSchema(String tableName, List<ColumnSchema> columns) {

    public record ColumnSchema(String name, String type) {
    }

    public List<String> columnNames() {
        return columns.stream().map(ColumnSchema::name).toList();
    }
}
