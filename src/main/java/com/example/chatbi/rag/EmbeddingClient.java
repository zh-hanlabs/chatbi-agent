package com.example.chatbi.rag;

public interface EmbeddingClient {

    int dimensions();

    float[] embed(String text);
}
