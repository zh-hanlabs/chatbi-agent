package com.example.chatbi.nl2sql;

import com.example.chatbi.api.UnsupportedQuestionException;
import org.junit.jupiter.api.Test;

import java.util.List;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

class RuleBasedSqlGeneratorTests {

    private final RuleBasedSqlGenerator generator = new RuleBasedSqlGenerator();

    @Test
    void gmvAliasesAreRecognized() {
        for (String question : List.of("北京的 GMV", "上海 gmv 是多少", "近7天的成交金额", "广州销售额")) {
            assertThat(generator.generate(question).metric()).isEqualTo("GMV");
        }
    }

    @Test
    void orderCountAliasesAreRecognized() {
        for (String question : List.of("总订单量", "北京订单数", "上海有多少单")) {
            assertThat(generator.generate(question).metric()).isEqualTo("ORDER_COUNT");
        }
    }

    @Test
    void refundQuestionWinsOverAmountKeywords() {
        // 「退款」优先于「金额」,退款类问题不被 GMV 抢走
        assertThat(generator.generate("北京退款金额是多少").metric()).isEqualTo("REFUND_RATE");
    }

    @Test
    void recentDaysParsingVariants() {
        assertThat(generator.generate("近7天北京的订单量").sql()).contains("TIMESTAMPADD(DAY, -7,");
        assertThat(generator.generate("最近30天的 GMV").sql()).contains("TIMESTAMPADD(DAY, -30,");
        assertThat(generator.generate("近7日订单量").sql()).contains("TIMESTAMPADD(DAY, -7,");
    }

    @Test
    void noTimeWindowOmitsTimestampCondition() {
        assertThat(generator.generate("北京的 GMV").sql()).doesNotContain("TIMESTAMPADD");
    }

    @Test
    void regionTriggersJoinAndFilter() {
        GeneratedSql sql = generator.generate("上海的订单量");
        assertThat(sql.sql()).contains("JOIN regions r");
        assertThat(sql.tablesUsed()).containsExactlyInAnyOrder("orders", "regions");
    }

    @Test
    void unsupportedQuestionThrowsWithGuidance() {
        assertThatThrownBy(() -> generator.generate("今天天气怎么样"))
                .isInstanceOf(UnsupportedQuestionException.class)
                .hasMessageContaining("GMV");
    }
}
