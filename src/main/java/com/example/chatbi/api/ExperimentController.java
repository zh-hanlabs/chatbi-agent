package com.example.chatbi.api;

import com.example.chatbi.eval.RagSweepExperimentService;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/experiments")
public class ExperimentController {

    private final RagSweepExperimentService experimentService;

    public ExperimentController(RagSweepExperimentService experimentService) {
        this.experimentService = experimentService;
    }

    /** chunk 尺寸 × TopK × 阈值 扫参对比,返回各配置命中率与最优配置 */
    @GetMapping("/rag-sweep")
    public ResponseEntity<RagSweepExperimentService.SweepReport> ragSweep() {
        return ResponseEntity.ok(experimentService.run());
    }
}
