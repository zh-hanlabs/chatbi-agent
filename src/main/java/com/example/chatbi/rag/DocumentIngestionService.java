package com.example.chatbi.rag;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.List;

/**
 * 文档入库管道:保存原文 → 段落切分 → 逐块向量化 → 落库。
 * 向量化失败时整体回滚,保证 documents 与 chunks 的一致性。
 */
@Service
public class DocumentIngestionService {

    public record IngestionResult(long documentId, String title, int chunkCount) {
    }

    private final DocumentRepository repository;
    private final TextChunker chunker;
    private final EmbeddingClient embeddingClient;
    private final ObjectMapper objectMapper;

    public DocumentIngestionService(DocumentRepository repository, TextChunker chunker,
            EmbeddingClient embeddingClient, ObjectMapper objectMapper) {
        this.repository = repository;
        this.chunker = chunker;
        this.embeddingClient = embeddingClient;
        this.objectMapper = objectMapper;
    }

    @Transactional
    public IngestionResult ingest(String title, String content) {
        long documentId = repository.insertDocument(title, content);
        List<String> chunks = chunker.chunk(content);
        for (int i = 0; i < chunks.size(); i++) {
            String chunk = chunks.get(i);
            float[] vector = embeddingClient.embed(chunk);
            repository.insertChunk(documentId, i, chunk, toJson(vector));
        }
        return new IngestionResult(documentId, title, chunks.size());
    }

    private String toJson(float[] vector) {
        try {
            return objectMapper.writeValueAsString(vector);
        } catch (JsonProcessingException e) {
            throw new IllegalStateException("向量序列化失败", e);
        }
    }
}
