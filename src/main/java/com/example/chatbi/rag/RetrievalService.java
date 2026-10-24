package com.example.chatbi.rag;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;

import java.util.Comparator;
import java.util.List;

/**
 * RAG 检索:问题向量化后与全部 chunk 向量算余弦,取 TopK。
 * 演示级语料全量扫描即可;换真实向量库时只改本类。
 */
@Service
public class RetrievalService {

    public record ScoredChunk(long documentId, String documentTitle, int chunkIndex, String content,
                              double score) {
    }

    private final DocumentRepository repository;
    private final EmbeddingClient embeddingClient;
    private final ObjectMapper objectMapper;
    private final int topK;

    public RetrievalService(DocumentRepository repository, EmbeddingClient embeddingClient,
            ObjectMapper objectMapper, @Value("${chatbi.rag.top-k:3}") int topK) {
        this.repository = repository;
        this.embeddingClient = embeddingClient;
        this.objectMapper = objectMapper;
        this.topK = topK;
    }

    public List<ScoredChunk> retrieve(String query) {
        float[] queryVector = embeddingClient.embed(query);
        var titlesById = repository.listDocuments().stream()
                .collect(java.util.stream.Collectors.toMap(DocumentRepository.DocumentRow::id,
                        DocumentRepository.DocumentRow::title));
        return repository.allChunks().stream()
                .map(chunk -> new ScoredChunk(chunk.documentId(),
                        titlesById.getOrDefault(chunk.documentId(), "?"),
                        chunk.chunkIndex(), chunk.content(),
                        VectorMath.cosine(queryVector, parseEmbedding(chunk.embedding()))))
                .filter(scored -> scored.score() > 0)
                .sorted(Comparator.comparingDouble(ScoredChunk::score).reversed())
                .limit(topK)
                .toList();
    }

    private float[] parseEmbedding(String json) {
        try {
            return objectMapper.readValue(json, float[].class);
        } catch (JsonProcessingException e) {
            throw new IllegalStateException("向量反序列化失败", e);
        }
    }
}
