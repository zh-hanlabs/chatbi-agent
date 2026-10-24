package com.example.chatbi.llm;

import com.example.chatbi.nl2sql.GeneratedSql;
import com.example.chatbi.nl2sql.SqlGenerator;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Primary;
import org.springframework.stereotype.Component;

/**
 * SqlGenerator 门面:配置了 API Key 且 LLM 生成成功 → 用 LLM 结果;
 * 未配置/调用失败/输出未过校验 → 回退规则实现。
 * 调用方(RagRouter/Nl2SqlController)只依赖本门面,切换实现零改动。
 */
@Component
@Primary
public class SqlGeneratorDelegate implements SqlGenerator {

    private static final Logger log = LoggerFactory.getLogger(SqlGeneratorDelegate.class);

    private final SqlGenerator ruleBased;
    private final SqlGenerator llm;
    private final LlmProperties properties;

    public SqlGeneratorDelegate(@Qualifier("ruleBasedSqlGenerator") SqlGenerator ruleBased,
            @Qualifier("llmSqlGenerator") SqlGenerator llm, LlmProperties properties) {
        this.ruleBased = ruleBased;
        this.llm = llm;
        this.properties = properties;
    }

    @Override
    public GeneratedSql generate(String question) {
        if (!properties.enabled()) {
            return ruleBased.generate(question);
        }
        try {
            return llm.generate(question);
        } catch (Exception e) {
            log.warn("LLM SQL 生成失败,回退规则实现: {}", e.getMessage());
            return ruleBased.generate(question);
        }
    }
}
