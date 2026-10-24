package com.example.chatbi.api;

import com.example.chatbi.nl2sql.BusinessSchemaService;
import com.example.chatbi.nl2sql.GeneratedSql;
import com.example.chatbi.nl2sql.SqlGenerator;
import com.example.chatbi.nl2sql.TableSchema;
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;

@RestController
@RequestMapping("/api")
public class Nl2SqlController {

    private final BusinessSchemaService schemaService;
    private final SqlGenerator sqlGenerator;

    public Nl2SqlController(BusinessSchemaService schemaService, SqlGenerator sqlGenerator) {
        this.schemaService = schemaService;
        this.sqlGenerator = sqlGenerator;
    }

    public record Nl2SqlRequest(@NotBlank String question) {
    }

    @GetMapping("/schema")
    public ResponseEntity<List<TableSchema>> schema() {
        return ResponseEntity.ok(schemaService.businessTables());
    }

    @PostMapping("/nl2sql")
    public ResponseEntity<GeneratedSql> generate(@Valid @RequestBody Nl2SqlRequest request) {
        return ResponseEntity.ok(sqlGenerator.generate(request.question()));
    }
}
