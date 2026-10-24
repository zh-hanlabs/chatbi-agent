package com.example.chatbi.api;

import com.example.chatbi.rag.DocumentIngestionService;
import com.example.chatbi.rag.DocumentRepository;
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;

@RestController
@RequestMapping("/api/documents")
public class DocumentController {

    private final DocumentIngestionService ingestionService;
    private final DocumentRepository repository;

    public DocumentController(DocumentIngestionService ingestionService, DocumentRepository repository) {
        this.ingestionService = ingestionService;
        this.repository = repository;
    }

    public record UploadRequest(@NotBlank String title, @NotBlank String content) {
    }

    @PostMapping
    public ResponseEntity<DocumentIngestionService.IngestionResult> upload(
            @Valid @RequestBody UploadRequest request) {
        return ResponseEntity.status(201).body(ingestionService.ingest(request.title(), request.content()));
    }

    @GetMapping
    public ResponseEntity<List<DocumentRepository.DocumentRow>> list() {
        return ResponseEntity.ok(repository.listDocuments());
    }

    @GetMapping("/{id}")
    public ResponseEntity<DocumentRepository.DocumentRow> detail(@PathVariable long id) {
        return ResponseEntity.ok(repository.findDocument(id)
                .orElseThrow(() -> new NotFoundException("文档不存在: " + id)));
    }

    @GetMapping("/{id}/chunks")
    public ResponseEntity<List<DocumentRepository.ChunkRow>> chunks(@PathVariable long id) {
        repository.findDocument(id).orElseThrow(() -> new NotFoundException("文档不存在: " + id));
        return ResponseEntity.ok(repository.findChunks(id));
    }
}
