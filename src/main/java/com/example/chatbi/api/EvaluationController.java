package com.example.chatbi.api;

import com.example.chatbi.eval.EvaluationService;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/evaluations")
public class EvaluationController {

    private final EvaluationService evaluationService;

    public EvaluationController(EvaluationService evaluationService) {
        this.evaluationService = evaluationService;
    }

    /** 跑全量评估集,返回总体与分类准确率及失败明细 */
    @GetMapping
    public ResponseEntity<EvaluationService.EvaluationReport> run() {
        return ResponseEntity.ok(evaluationService.run());
    }
}
