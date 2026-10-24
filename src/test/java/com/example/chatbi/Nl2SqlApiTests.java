package com.example.chatbi;

import com.example.chatbi.nl2sql.GeneratedSql;
import com.example.chatbi.nl2sql.SqlGenerator;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.web.servlet.MockMvc;

import java.util.List;

import static org.assertj.core.api.Assertions.assertThat;
import static org.hamcrest.Matchers.hasItem;
import static org.hamcrest.Matchers.not;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
@ActiveProfiles("test")
class Nl2SqlApiTests {

    @Autowired
    private MockMvc mockMvc;

    @Autowired
    private SqlGenerator sqlGenerator;

    @Autowired
    private JdbcTemplate jdbcTemplate;

    @Test
    void generatedSqlExecutesAgainstDemoData() {
        for (String question : List.of("北京的 GMV", "上海的订单量", "广州的退款率", "近7天的 GMV")) {
            GeneratedSql generated = sqlGenerator.generate(question);
            assertThat(generated.sql()).startsWith("SELECT");
            assertThat(jdbcTemplate.queryForMap(generated.sql())).isNotEmpty();
        }
    }

    @Test
    void schemaExposesOnlyBusinessTables() throws Exception {
        mockMvc.perform(get("/api/schema"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.length()").value(3))
                .andExpect(jsonPath("$[*].tableName", hasItem("orders")))
                .andExpect(jsonPath("$[*].tableName", hasItem("products")))
                .andExpect(jsonPath("$[*].tableName", hasItem("regions")))
                .andExpect(jsonPath("$[*].tableName", not(hasItem("users"))))
                .andExpect(jsonPath("$[*].tableName", not(hasItem("conversations"))))
                .andExpect(jsonPath("$[*].tableName", not(hasItem("messages"))))
                .andExpect(jsonPath("$[*].tableName", not(hasItem("audit_logs"))));
    }

    @Test
    void schemaContainsOrderColumns() throws Exception {
        mockMvc.perform(get("/api/schema"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$[0].columns[*].name", hasItem("amount")))
                .andExpect(jsonPath("$[0].columns[*].name", hasItem("status")))
                .andExpect(jsonPath("$[0].columns[*].name", hasItem("region_id")));
    }

    @Test
    void gmvQuestionWithRegionGeneratesCompletedSumSql() throws Exception {
        mockMvc.perform(post("/api/nl2sql")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"userId\":3,\"question\":\"北京上个月的 GMV 是多少\"}"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.metric").value("GMV"))
                .andExpect(jsonPath("$.sql").value(
                        "SELECT SUM(o.amount) AS gmv FROM orders o JOIN regions r ON r.id = o.region_id "
                                + "WHERE o.status = 'COMPLETED' AND r.name = '北京'"))
                .andExpect(jsonPath("$.tablesUsed", hasItem("orders")))
                .andExpect(jsonPath("$.tablesUsed", hasItem("regions")))
                .andExpect(jsonPath("$.explanation").value("统计北京区域已完成订单的金额总和"));
    }

    @Test
    void orderCountQuestionWithoutRegionHasNoJoin() throws Exception {
        mockMvc.perform(post("/api/nl2sql")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"userId\":3,\"question\":\"总订单量有多少\"}"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.metric").value("ORDER_COUNT"))
                .andExpect(jsonPath("$.sql").value("SELECT COUNT(*) AS order_count FROM orders o"));
    }

    @Test
    void refundRateQuestionUsesCaseWhen() throws Exception {
        mockMvc.perform(post("/api/nl2sql")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"userId\":3,\"question\":\"上海的退款率\"}"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.metric").value("REFUND_RATE"))
                .andExpect(jsonPath("$.sql").value(
                        "SELECT SUM(CASE WHEN o.status = 'REFUNDED' THEN 1 ELSE 0 END) * 1.0 / COUNT(*) AS refund_rate "
                                + "FROM orders o JOIN regions r ON r.id = o.region_id WHERE r.name = '上海'"));
    }

    @Test
    void recentDaysQuestionAddsTimeWindow() throws Exception {
        mockMvc.perform(post("/api/nl2sql")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"userId\":3,\"question\":\"近7天北京的订单量\"}"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.metric").value("ORDER_COUNT"))
                .andExpect(jsonPath("$.sql").value(
                        "SELECT COUNT(*) AS order_count FROM orders o JOIN regions r ON r.id = o.region_id "
                                + "WHERE r.name = '北京' AND o.created_at >= TIMESTAMPADD(DAY, -7, CURRENT_TIMESTAMP)"));
    }

    @Test
    void unrecognizedQuestionIsRejected() throws Exception {
        mockMvc.perform(post("/api/nl2sql")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"userId\":3,\"question\":\"今天天气怎么样\"}"))
                .andExpect(status().isUnprocessableEntity())
                .andExpect(jsonPath("$.error").isNotEmpty());
    }

    @Test
    void blankQuestionIsRejected() throws Exception {
        mockMvc.perform(post("/api/nl2sql")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"userId\":3,\"question\":\" \"}"))
                .andExpect(status().isBadRequest());
    }
}
