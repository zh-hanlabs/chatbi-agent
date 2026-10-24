package com.example.chatbi.rag;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;

import java.util.List;

/**
 * 引用式回答:Top1 命中即作为抽取式答案,同时返回全部引用(文档标题/块号/得分)。
 * 最高相似度低于阈值时拒答,不编造内容。
 */
@Service
public class RagAnswerService {

    public record RagAnswer(String answer, List<RetrievalService.ScoredChunk> citations, boolean refused) {
    }

    private final RetrievalService retrievalService;
    private final double minScore;

    public RagAnswerService(RetrievalService retrievalService,
            @Value("${chatbi.rag.min-score:0.2}") double minScore) {
        this.retrievalService = retrievalService;
        this.minScore = minScore;
    }

    public RagAnswer answer(String question) {
        List<RetrievalService.ScoredChunk> hits = retrievalService.retrieve(question);
        if (hits.isEmpty() || hits.getFirst().score() < minScore) {
            return new RagAnswer("知识库中未找到与该问题相关的内容,请换个问法或先上传相关文档。", List.of(), true);
        }
        return new RagAnswer(hits.getFirst().content(), hits, false);
    }
}
