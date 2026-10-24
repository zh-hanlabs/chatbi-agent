package com.example.chatbi.nl2sql;

import org.springframework.stereotype.Service;

import java.util.Set;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/**
 * NL2SQL 产出的 SQL 在执行前的只读安全校验。
 * 规则是保守的:宁可误拒也不放过,任何无法确认安全的写法一律拒绝。
 */
@Service
public class SqlSecurityValidator {

    private static final Set<String> ALLOWED_TABLES = Set.of("orders", "products", "regions");

    /** 敏感字段:任何位置出现都拒绝,防止明细泄露与布尔探测 */
    private static final Pattern SENSITIVE_COLUMN = Pattern.compile("\\bcustomer_phone\\b",
            Pattern.CASE_INSENSITIVE);

    /**
     * 写操作与危险动词。这些词在受认可的只读查询中没有合法出现场景:
     * FOR UPDATE 含 update、LOCK IN SHARE MODE 含 lock、INTO OUTFILE 含 outfile,
     * 均被同一条扫描覆盖;benchmark/sleep 用于拦截变相 DoS。
     */
    private static final Pattern FORBIDDEN_VERB = Pattern.compile(
            "\\b(insert|update|delete|replace|merge|drop|alter|create|truncate|rename|grant|revoke|"
                    + "lock|unlock|call|execute|set|use|load|handler|kill|shutdown|outfile|dumpfile|"
                    + "benchmark|sleep|procedure)\\b",
            Pattern.CASE_INSENSITIVE);

    /** 投影通配符:SELECT *、o.* 与列表中的裸 * 都会绕过列级控制,一律拒绝 */
    private static final Pattern PROJECTION_WILDCARD = Pattern.compile(
            "(\\bselect\\s+\\*)|(\\w+\\.\\*)|(\\*\\s*(,|from))", Pattern.CASE_INSENSITIVE);

    private static final Pattern STRING_LITERAL = Pattern.compile("'[^']*'");

    /** MySQL 反引号与 ANSI 双引号标识符可以绕过表名白名单的词法识别,直接禁用 */
    private static final Pattern IDENTIFIER_QUOTE = Pattern.compile("[`\"]");

    private static final Pattern TABLE_REFERENCE = Pattern.compile(
            "\\b(from|join)\\s+([a-zA-Z_][a-zA-Z0-9_]*)", Pattern.CASE_INSENSITIVE);

    public ValidationResult validate(String rawSql) {
        if (rawSql == null || rawSql.isBlank()) {
            return ValidationResult.rejected("SQL 为空");
        }
        String sql = rawSql.strip();
        while (sql.endsWith(";")) {
            sql = sql.substring(0, sql.length() - 1).stripTrailing();
        }
        // 先剔除字符串字面量再做关键字扫描,避免字面量内容被误判或被用来藏payload
        String stripped = STRING_LITERAL.matcher(sql).replaceAll("''");

        if (stripped.contains(";")) {
            return ValidationResult.rejected("仅允许单条语句");
        }
        if (stripped.contains("--") || stripped.contains("/*") || stripped.contains("#")) {
            return ValidationResult.rejected("不允许出现注释");
        }
        if (!startsWithSelect(sql)) {
            return ValidationResult.rejected("仅允许 SELECT 查询");
        }
        if (IDENTIFIER_QUOTE.matcher(stripped).find()) {
            return ValidationResult.rejected("不允许使用反引号或双引号标识符");
        }
        Matcher forbidden = FORBIDDEN_VERB.matcher(stripped);
        if (forbidden.find()) {
            return ValidationResult.rejected("包含禁止的关键字: " + forbidden.group().toLowerCase());
        }
        if (SENSITIVE_COLUMN.matcher(stripped).find()) {
            return ValidationResult.rejected("包含敏感字段: customer_phone");
        }
        if (PROJECTION_WILDCARD.matcher(stripped).find()) {
            return ValidationResult.rejected("不允许使用 SELECT * 通配符,请明确列出字段");
        }
        Matcher tableRef = TABLE_REFERENCE.matcher(stripped);
        while (tableRef.find()) {
            String table = tableRef.group(2).toLowerCase();
            if (!ALLOWED_TABLES.contains(table)) {
                return ValidationResult.rejected("不允许访问表: " + table);
            }
        }
        return ValidationResult.ok();
    }

    private boolean startsWithSelect(String sql) {
        if (sql.length() < 6 || !sql.substring(0, 6).equalsIgnoreCase("select")) {
            return false;
        }
        if (sql.length() == 6) {
            return true;
        }
        char next = sql.charAt(6);
        return Character.isWhitespace(next) || next == '(' || next == '*';
    }
}
