package com.example.chatbi.api;

import com.example.chatbi.authz.PermissionService;
import com.example.chatbi.nl2sql.BusinessSchemaService;
import com.example.chatbi.nl2sql.GeneratedSql;
import com.example.chatbi.nl2sql.SqlGenerator;
import com.example.chatbi.nl2sql.TableSchema;
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
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
    private final PermissionService permissionService;

    public Nl2SqlController(BusinessSchemaService schemaService, SqlGenerator sqlGenerator,
            PermissionService permissionService) {
        this.schemaService = schemaService;
        this.sqlGenerator = sqlGenerator;
        this.permissionService = permissionService;
    }

    public record Nl2SqlRequest(@NotNull Long userId, @NotBlank String question) {
    }

    @GetMapping("/schema")
    public ResponseEntity<List<TableSchema>> schema() {
        return ResponseEntity.ok(schemaService.businessTables());
    }

    @PostMapping("/nl2sql")
    public ResponseEntity<GeneratedSql> generate(@Valid @RequestBody Nl2SqlRequest request) {
        GeneratedSql generated = sqlGenerator.generate(request.question());
        permissionService.checkMetricAndRegion(request.userId(), generated.metric(), null);
        permissionService.checkRegionsInSql(request.userId(), generated.sql());
        return ResponseEntity.ok(generated);
    }
}
