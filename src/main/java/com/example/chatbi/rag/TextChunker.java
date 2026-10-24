package com.example.chatbi.rag;

import org.springframework.stereotype.Component;

import java.util.ArrayList;
import java.util.List;

/**
 * 段落优先的切分器:按空行分段,段打包为目标长度的块;
 * 超长段落硬切并保留相邻块的首尾重叠,保证跨块语义不断裂。
 */
@Component
public class TextChunker {

    public static final int TARGET_CHUNK_SIZE = 500;
    public static final int OVERLAP_SIZE = 50;

    public List<String> chunk(String content) {
        List<String> chunks = new ArrayList<>();
        if (content == null || content.isBlank()) {
            return chunks;
        }
        StringBuilder buffer = new StringBuilder();
        for (String paragraph : content.split("\\n\\s*\\n")) {
            String trimmed = paragraph.strip();
            if (trimmed.isEmpty()) {
                continue;
            }
            if (trimmed.length() > TARGET_CHUNK_SIZE) {
                flush(chunks, buffer);
                chunks.addAll(splitLongParagraph(trimmed));
            } else if (buffer.length() + trimmed.length() + 1 > TARGET_CHUNK_SIZE && buffer.length() > 0) {
                flush(chunks, buffer);
                buffer.append(trimmed);
            } else {
                if (buffer.length() > 0) {
                    buffer.append('\n');
                }
                buffer.append(trimmed);
            }
        }
        flush(chunks, buffer);
        return chunks;
    }

    private List<String> splitLongParagraph(String paragraph) {
        List<String> parts = new ArrayList<>();
        int step = TARGET_CHUNK_SIZE - OVERLAP_SIZE;
        for (int start = 0; start < paragraph.length(); start += step) {
            int end = Math.min(start + TARGET_CHUNK_SIZE, paragraph.length());
            parts.add(paragraph.substring(start, end));
            if (end == paragraph.length()) {
                break;
            }
        }
        return parts;
    }

    private void flush(List<String> chunks, StringBuilder buffer) {
        if (buffer.length() > 0) {
            chunks.add(buffer.toString());
            buffer.setLength(0);
        }
    }
}
