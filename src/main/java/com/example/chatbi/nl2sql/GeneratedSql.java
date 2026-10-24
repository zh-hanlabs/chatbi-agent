package com.example.chatbi.nl2sql;

import java.util.List;

public record GeneratedSql(String sql, String metric, List<String> tablesUsed, String explanation) {
}
