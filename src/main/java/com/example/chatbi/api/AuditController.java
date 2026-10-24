package com.example.chatbi.api;

import com.example.chatbi.audit.AuditService;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;

/** 管理端:审计日志查询,仅 ADMIN 角色可访问 */
@RestController
@RequestMapping("/api/audit")
public class AuditController {

    private final AuditService auditService;

    public AuditController(AuditService auditService) {
        this.auditService = auditService;
    }

    @GetMapping
    public ResponseEntity<List<AuditService.AuditEntry>> list(@RequestParam long userId,
            @RequestParam(defaultValue = "50") int limit) {
        if (!auditService.isAdmin(userId)) {
            throw new ForbiddenException("仅管理员可查询审计日志");
        }
        return ResponseEntity.ok(auditService.listRecent(limit));
    }
}
