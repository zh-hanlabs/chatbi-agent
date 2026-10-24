package com.example.chatbi.llm;

import com.example.chatbi.api.UnsupportedQuestionException;
import com.example.chatbi.nl2sql.BusinessSchemaService;
import com.example.chatbi.nl2sql.GeneratedSql;
import com.example.chatbi.nl2sql.RuleBasedSqlGenerator;
import com.example.chatbi.nl2sql.SqlGenerator;
import com.example.chatbi.nl2sql.SqlSecurityValidator;
import org.junit.jupiter.api.Test;
import org.mockito.Mockito;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.when;

class LlmGeneratorDelegateTests {

    private final SqlGenerator rule = new RuleBasedSqlGenerator();
    private final SqlSecurityValidator validator = new SqlSecurityValidator();
    private final BusinessSchemaService schemaService = Mockito.mock(BusinessSchemaService.class);

    private LlmSqlGenerator llmGeneratorReturning(String content) {
        OpenAiCompatChatModel model = Mockito.mock(OpenAiCompatChatModel.class);
        when(model.complete(anyString(), anyString())).thenReturn(content);
        return new LlmSqlGenerator(model, schemaService, validator, new com.fasterxml.jackson.databind.ObjectMapper());
    }

    private SqlGeneratorDelegate delegate(SqlGenerator llm, boolean enabled) {
        return new SqlGeneratorDelegate(rule, llm,
                new LlmProperties("http://x", enabled ? "key" : "", "m", "e", 5));
    }

    @Test
    void disabledKeyUsesRuleImplementation() {
        SqlGeneratorDelegate delegate = delegate(llmGeneratorReturning("垃圾输出"), false);

        GeneratedSql result = delegate.generate("北京的 GMV");
        assertThat(result.metric()).isEqualTo("GMV");
        assertThat(result.sql()).contains("SUM(o.amount)");
    }

    @Test
    void validLlmJsonIsUsed() {
        String content = "{\"metric\":\"GMV\",\"sql\":\"SELECT SUM(o.amount) AS gmv FROM orders o "
                + "WHERE o.status = 'COMPLETED'\",\"explanation\":\"LLM 口径\"}";
        SqlGeneratorDelegate delegate = delegate(llmGeneratorReturning(content), true);

        GeneratedSql result = delegate.generate("总成交金额");
        assertThat(result.explanation()).isEqualTo("LLM 口径");
        assertThat(result.sql()).contains("SUM(o.amount)");
    }

    @Test
    void markdownFencedJsonIsTolerated() {
        String content = "```json\n{\"metric\":\"ORDER_COUNT\",\"sql\":\"SELECT COUNT(*) AS c FROM orders\","
                + "\"explanation\":\"订单数\"}\n```";
        SqlGeneratorDelegate delegate = delegate(llmGeneratorReturning(content), true);

        assertThat(delegate.generate("订单数").metric()).isEqualTo("ORDER_COUNT");
    }

    @Test
    void nullMetricMeansUnsupportedQuestion() {
        String content = "{\"metric\":null}";
        LlmSqlGenerator generator = llmGeneratorReturning(content);

        assertThatThrownBy(() -> generator.generate("今天天气怎么样"))
                .isInstanceOf(UnsupportedQuestionException.class);
    }

    @Test
    void unsafeLlmSqlFallsBackToRules() {
        // LLM 产出 DELETE → 校验器拒绝 → 门面回退规则实现
        String content = "{\"metric\":\"GMV\",\"sql\":\"DELETE FROM orders\",\"explanation\":\"x\"}";
        SqlGeneratorDelegate delegate = delegate(llmGeneratorReturning(content), true);

        GeneratedSql result = delegate.generate("北京的 GMV");
        assertThat(result.sql()).contains("SELECT");
    }

    @Test
    void httpFailureFallsBackToRules() {
        OpenAiCompatChatModel model = Mockito.mock(OpenAiCompatChatModel.class);
        when(model.complete(anyString(), anyString()))
                .thenThrow(new OpenAiCompatChatModel.LlmUnavailableException("timeout"));
        SqlGeneratorDelegate delegate = delegate(new LlmSqlGenerator(model, schemaService, validator,
                new com.fasterxml.jackson.databind.ObjectMapper()), true);

        GeneratedSql result = delegate.generate("北京的 GMV");
        assertThat(result.metric()).isEqualTo("GMV");
        assertThat(result.sql()).contains("SUM(o.amount)");
    }

    @Test
    void unparseableOutputFallsBackToRules() {
        SqlGeneratorDelegate delegate = delegate(llmGeneratorReturning("模型自由发挥文本"), true);

        assertThat(delegate.generate("北京的 GMV").metric()).isEqualTo("GMV");
    }
}
