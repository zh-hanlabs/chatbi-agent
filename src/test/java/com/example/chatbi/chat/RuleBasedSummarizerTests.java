package com.example.chatbi.chat;

import org.junit.jupiter.api.Test;

import java.util.List;

import static org.assertj.core.api.Assertions.assertThat;

class RuleBasedSummarizerTests {

    private final RuleBasedSummarizer summarizer = new RuleBasedSummarizer();

    private ChatMessage of(String role, String content, String toolCall) {
        return new ChatMessage(1L, "c", role, content, toolCall, null);
    }

    @Test
    void emptyHistorySummarizesToZeroQuestions() {
        assertThat(summarizer.summarize(List.of())).isEqualTo("此前对话共 0 次提问。");
    }

    @Test
    void countsDistinctQuestionsButAllAttempts() {
        String summary = summarizer.summarize(List.of(
                of("USER", "北京的GMV", null),
                of("ASSISTANT", "SQL...", "{}"),
                of("USER", "北京的GMV", null),
                of("ASSISTANT", "SQL...", "{}")));

        assertThat(summary).isEqualTo("此前对话共 2 次提问,主要问题: 北京的GMV;其间生成过 2 次查询工具调用。");
    }

    @Test
    void capsQuestionListAtThree() {
        String summary = summarizer.summarize(List.of(
                of("USER", "q1", null), of("USER", "q2", null),
                of("USER", "q3", null), of("USER", "q4", null)));

        assertThat(summary).contains("q1").contains("q2").contains("q3").doesNotContain("q4");
    }
}
