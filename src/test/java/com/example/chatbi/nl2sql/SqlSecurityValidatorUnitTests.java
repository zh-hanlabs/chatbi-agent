package com.example.chatbi.nl2sql;

import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;

class SqlSecurityValidatorUnitTests {

    private final SqlSecurityValidator validator = new SqlSecurityValidator();

    @Test
    void allowedFormsIncludeLowercaseAndTrailingSemicolon() {
        for (String sql : java.util.List.of(
                "select count(*) from orders",
                "SELECT o.amount FROM orders o  ; ",
                "SELECT COUNT(*) AS c FROM regions WHERE name = 'a;b'")) {
            assertThat(validator.validate(sql).allowed()).as(sql).isTrue();
        }
    }

    @Test
    void bareSelectWithoutFromIsAllowed() {
        assertThat(validator.validate("SELECT 1").allowed()).isTrue();
    }

    @Test
    void rejectionReasonsAreActionable() {
        assertThat(validator.validate("SELECT 1; DELETE FROM orders").reason()).contains("单条语句");
        assertThat(validator.validate("SELECT 1 -- x").reason()).contains("注释");
        assertThat(validator.validate("UPDATE orders SET amount = 0").reason()).contains("仅允许 SELECT");
        assertThat(validator.validate("SELECT amount FROM orders PROCEDURE analyse()").reason()).contains("禁止的关键字");
        assertThat(validator.validate("SELECT customer_phone FROM orders").reason()).contains("敏感字段");
        assertThat(validator.validate("SELECT * FROM orders").reason()).contains("通配符");
        assertThat(validator.validate("SELECT username FROM users").reason()).contains("不允许访问表");
    }

    @Test
    void subqueryInnerTableIsStillWhitelistChecked() {
        assertThat(validator.validate("SELECT t.a FROM (SELECT a FROM orders) t").allowed()).isTrue();
        assertThat(validator.validate("SELECT t.a FROM (SELECT username FROM users) t").allowed()).isFalse();
    }

    @Test
    void nullAndBlankAreRejected() {
        assertThat(validator.validate(null).allowed()).isFalse();
        assertThat(validator.validate("   ").allowed()).isFalse();
    }

    @Test
    void arithmeticStarIsNotWildcard() {
        // 退款率 SQL 里的 * 1.0 与 COUNT(*) 不被通配符规则误伤
        String refundSql = "SELECT SUM(CASE WHEN o.status = 'REFUNDED' THEN 1 ELSE 0 END) * 1.0 / COUNT(*) "
                + "AS refund_rate FROM orders o";
        assertThat(validator.validate(refundSql).allowed()).isTrue();
    }
}
