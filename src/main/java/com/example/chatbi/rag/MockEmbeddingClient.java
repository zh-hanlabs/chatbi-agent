package com.example.chatbi.rag;

import org.springframework.stereotype.Component;

import java.util.ArrayList;
import java.util.List;
import java.util.Locale;

/**
 * 确定性向量实现:token 哈希投影 + L2 归一化。
 * 同一文本得到同一向量;中英文混合时 CJK 按二元组(bigram)切分,
 * 相似文本共享大量 bigram,余弦相似度足以支撑演示级检索。
 * 接入真实 Embedding API 后由新实现替换本类,调用方无感。
 */
@Component
public class MockEmbeddingClient implements EmbeddingClient {

    public static final int DIMENSIONS = 128;

    @Override
    public int dimensions() {
        return DIMENSIONS;
    }

    @Override
    public float[] embed(String text) {
        float[] vector = new float[DIMENSIONS];
        if (text == null || text.isBlank()) {
            return vector;
        }
        for (String token : tokenize(text)) {
            int index = Math.floorMod(token.hashCode(), DIMENSIONS);
            vector[index] += 1.0f;
        }
        float norm = 0;
        for (float v : vector) {
            norm += v * v;
        }
        norm = (float) Math.sqrt(norm);
        if (norm > 0) {
            for (int i = 0; i < vector.length; i++) {
                vector[i] /= norm;
            }
        }
        return vector;
    }

    /** 拉丁词按词切,CJK 连续段按相邻二元组切,标点丢弃 */
    private List<String> tokenize(String text) {
        List<String> tokens = new ArrayList<>();
        StringBuilder word = new StringBuilder();
        int cjkStart = -1;

        for (int i = 0; i < text.length(); i++) {
            char ch = text.charAt(i);
            if (isCjk(ch)) {
                flushWord(tokens, word);
                if (cjkStart < 0) {
                    cjkStart = i;
                }
            } else {
                if (cjkStart >= 0) {
                    emitBigrams(text.substring(cjkStart, i), tokens);
                    cjkStart = -1;
                }
                if (Character.isLetterOrDigit(ch)) {
                    word.append(ch);
                } else {
                    flushWord(tokens, word);
                }
            }
        }
        if (cjkStart >= 0) {
            emitBigrams(text.substring(cjkStart), tokens);
        }
        flushWord(tokens, word);
        return tokens;
    }

    private void flushWord(List<String> tokens, StringBuilder word) {
        if (word.length() > 0) {
            tokens.add(word.toString().toLowerCase(Locale.ROOT));
            word.setLength(0);
        }
    }

    private void emitBigrams(String segment, List<String> tokens) {
        if (segment.length() == 1) {
            tokens.add(segment);
            return;
        }
        for (int i = 0; i + 1 < segment.length(); i++) {
            tokens.add(segment.substring(i, i + 2));
        }
    }

    private boolean isCjk(char ch) {
        Character.UnicodeScript script = Character.UnicodeScript.of(ch);
        return script == Character.UnicodeScript.HAN
                || script == Character.UnicodeScript.HIRAGANA
                || script == Character.UnicodeScript.KATAKANA
                || script == Character.UnicodeScript.HANGUL;
    }
}
