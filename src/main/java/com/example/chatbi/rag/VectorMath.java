package com.example.chatbi.rag;

final class VectorMath {

    private VectorMath() {
    }

    /** 向量已 L2 归一化时点积即余弦相似度 */
    static float cosine(float[] a, float[] b) {
        int length = Math.min(a.length, b.length);
        float dot = 0;
        for (int i = 0; i < length; i++) {
            dot += a[i] * b[i];
        }
        return dot;
    }
}
