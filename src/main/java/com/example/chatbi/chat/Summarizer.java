package com.example.chatbi.chat;

import java.util.List;

/**
 * 对话摘要抽象:把一段历史消息压成一句可放进提示词的概要。
 * 当前为规则实现,接入大模型后替换实现即可。
 */
public interface Summarizer {

    String summarize(List<ChatMessage> messages);
}
