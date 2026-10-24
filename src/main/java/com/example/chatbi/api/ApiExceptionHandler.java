package com.example.chatbi.api;

import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

import java.util.Map;

@RestControllerAdvice
public class ApiExceptionHandler {

    @ExceptionHandler(NotFoundException.class)
    public ResponseEntity<Map<String, String>> notFound(NotFoundException e) {
        return ResponseEntity.status(404).body(Map.of("error", e.getMessage()));
    }

    @ExceptionHandler(UnsupportedQuestionException.class)
    public ResponseEntity<Map<String, String>> unsupportedQuestion(UnsupportedQuestionException e) {
        return ResponseEntity.unprocessableEntity().body(Map.of("error", e.getMessage()));
    }

    @ExceptionHandler(SqlNotAllowedException.class)
    public ResponseEntity<Map<String, String>> sqlNotAllowed(SqlNotAllowedException e) {
        return ResponseEntity.unprocessableEntity().body(Map.of("error", e.getMessage()));
    }

    @ExceptionHandler(ForbiddenException.class)
    public ResponseEntity<Map<String, String>> forbidden(ForbiddenException e) {
        return ResponseEntity.status(403).body(Map.of("error", e.getMessage()));
    }

    /** 数据权限越权(区域/指标),生成层入口统一 403 */
    @ExceptionHandler(PermissionDeniedException.class)
    public ResponseEntity<Map<String, String>> permissionDenied(PermissionDeniedException e) {
        return ResponseEntity.status(403).body(Map.of("error", e.getMessage()));
    }

    /** 安全校验通过但 SQL 本身有误(列/表不存在、语法错),是客户端问题而非服务端故障 */
    @ExceptionHandler(org.springframework.jdbc.BadSqlGrammarException.class)
    public ResponseEntity<Map<String, String>> badSqlGrammar(org.springframework.jdbc.BadSqlGrammarException e) {
        return ResponseEntity.unprocessableEntity()
                .body(Map.of("error", "SQL 执行失败: 语法错误或引用了不存在的表/列"));
    }

    /** 慢查询触发 5 秒超时兜底,提示缩小范围而非报 500 */
    @ExceptionHandler(org.springframework.dao.QueryTimeoutException.class)
    public ResponseEntity<Map<String, String>> queryTimeout(org.springframework.dao.QueryTimeoutException e) {
        return ResponseEntity.status(504).body(Map.of("error", "查询超时,请缩小时间范围或加过滤条件后重试"));
    }
}
