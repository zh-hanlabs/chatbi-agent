package com.example.chatbi.chat;

import org.springframework.stereotype.Component;

import java.util.List;

/**
 * 规则式摘要:保留提问主线(去重、限量)与工具调用次数,
 * 足以让压缩后的上下文不丢失「用户在问什么」。
 */
@Component
public class RuleBasedSummarizer implements Summarizer {

    static final int MAX_QUESTIONS = 3;

    @Override
    public String summarize(List<ChatMessage> messages) {
        long questionCount = messages.stream().filter(message -> "USER".equals(message.role())).count();
        List<String> questions = messages.stream()
                .filter(message -> "USER".equals(message.role()))
                .map(ChatMessage::content)
                .distinct()
                .limit(MAX_QUESTIONS)
                .toList();
        long toolCalls = messages.stream()
                .filter(message -> message.toolCallJson() != null)
                .count();

        StringBuilder summary = new StringBuilder("此前对话共 ").append(questionCount).append(" 次提问");
        if (!questions.isEmpty()) {
            summary.append(",主要问题: ").append(String.join(" / ", questions));
        }
        if (toolCalls > 0) {
            summary.append(";其间生成过 ").append(toolCalls).append(" 次查询工具调用");
        }
        summary.append("。");
        return summary.toString();
    }
}
