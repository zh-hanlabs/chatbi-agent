package com.example.chatbi.api;

import com.example.chatbi.nl2sql.SqlExecutionService;
import com.example.chatbi.nl2sql.SqlSecurityValidator;
import com.example.chatbi.nl2sql.ValidationResult;
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/sql")
public class SqlController {

    private final SqlSecurityValidator validator;
    private final SqlExecutionService executionService;

    public SqlController(SqlSecurityValidator validator, SqlExecutionService executionService) {
        this.validator = validator;
        this.executionService = executionService;
    }

    public record ValidateRequest(@NotBlank String sql) {
    }

    public record ConfirmRequest(@NotNull Long userId, String conversationId, @NotBlank String sql) {
    }

    /** 预检:不执行,仅返回是否允许与原因,供确认页展示 */
    @PostMapping("/validate")
    public ResponseEntity<ValidationResult> validate(@Valid @RequestBody ValidateRequest request) {
        return ResponseEntity.ok(validator.validate(request.sql()));
    }

    /** 执行前确认:服务端重新校验后执行,返回列、行、是否截断与是否缓存命中;每次尝试均落审计 */
    @PostMapping("/confirm")
    public ResponseEntity<SqlExecutionService.SqlExecutionResult> confirm(@Valid @RequestBody ConfirmRequest request) {
        return ResponseEntity.ok(executionService.confirmAndExecute(request.userId(), request.conversationId(),
                request.sql()));
    }
}
