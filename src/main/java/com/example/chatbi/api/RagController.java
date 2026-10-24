package com.example.chatbi.api;

import com.example.chatbi.rag.RagRouter;
import com.example.chatbi.rag.RetrievalService;
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/rag")
public class RagController {

    private final RagRouter ragRouter;
    private final RetrievalService retrievalService;

    public RagController(RagRouter ragRouter, RetrievalService retrievalService) {
        this.ragRouter = ragRouter;
        this.retrievalService = retrievalService;
    }

    public record RagRequest(@NotBlank String question) {
    }

    /** 完整路由:NL2SQL → RAG 引用回答 → 拒答 */
    @PostMapping("/query")
    public ResponseEntity<RagRouter.RoutedAnswer> query(@Valid @RequestBody RagRequest request) {
        return ResponseEntity.ok(ragRouter.route(request.question()));
    }

    /** 仅检索:返回 TopK 相关块与得分,便于调参与演示 */
    @PostMapping("/retrieve")
    public ResponseEntity<java.util.List<RetrievalService.ScoredChunk>> retrieve(
            @Valid @RequestBody RagRequest request) {
        return ResponseEntity.ok(retrievalService.retrieve(request.question()));
    }
}
