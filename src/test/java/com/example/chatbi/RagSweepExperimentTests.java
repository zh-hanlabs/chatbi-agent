package com.example.chatbi;

import com.example.chatbi.eval.RagSweepExperimentService;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.ActiveProfiles;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest
@ActiveProfiles("test")
class RagSweepExperimentTests {

    @Autowired
    private RagSweepExperimentService experimentService;

    @Test
    void sweepProducesAllConfigsWithSaneMetrics() {
        RagSweepExperimentService.SweepReport report = experimentService.run();

        // 3 chunk 尺寸 × 2 TopK × 3 阈值
        assertThat(report.rows()).hasSize(18);
        assertThat(report.rows()).allSatisfy(row -> {
            assertThat(row.ragCases()).isEqualTo(15);
            assertThat(row.refusalCases()).isEqualTo(10);
            assertThat(row.ragHitRate()).isBetween(0.0, 1.0);
            assertThat(row.refusalAccuracy()).isBetween(0.0, 1.0);
        });

        // TopK 放宽应不降低召回:同一 chunk/阈值下 topK=3 命中率 >= topK=1
        for (RagSweepExperimentService.SweepRow top1 : report.rows()) {
            if (top1.config().topK() != 1) {
                continue;
            }
            report.rows().stream()
                    .filter(r -> r.config().topK() == 3
                            && r.config().chunkSize() == top1.config().chunkSize()
                            && r.config().minScore() == top1.config().minScore())
                    .findFirst()
                    .ifPresent(top3 -> assertThat(top3.ragHitRate()).isGreaterThanOrEqualTo(top1.ragHitRate()));
        }

        // 阈值收紧应不降低拒答准确率:同 chunk/TopK 下 minScore=0.3 拒答 >= 0.1
        for (RagSweepExperimentService.SweepRow loose : report.rows()) {
            if (loose.config().minScore() != 0.1) {
                continue;
            }
            report.rows().stream()
                    .filter(r -> r.config().minScore() == 0.3
                            && r.config().chunkSize() == loose.config().chunkSize()
                            && r.config().topK() == loose.config().topK())
                    .findFirst()
                    .ifPresent(tight -> assertThat(tight.refusalAccuracy())
                            .isGreaterThanOrEqualTo(loose.refusalAccuracy()));
        }

        printReport(report);
    }

    private void printReport(RagSweepExperimentService.SweepReport report) {
        System.out.println("=== RAG sweep ===");
        System.out.println("chunk overlap topK minScore ragHit refusalAcc");
        for (RagSweepExperimentService.SweepRow row : report.rows()) {
            System.out.printf("%5d %7d %4d %8.2f %6.2f %10.2f%n",
                    row.config().chunkSize(), row.config().overlap(), row.config().topK(),
                    row.config().minScore(), row.ragHitRate(), row.refusalAccuracy());
        }
        System.out.printf("best: chunk=%d topK=%d minScore=%.2f ragHit=%.2f refusalAcc=%.2f%n",
                report.bestByRagHit().config().chunkSize(), report.bestByRagHit().config().topK(),
                report.bestByRagHit().config().minScore(), report.bestByRagHit().ragHitRate(),
                report.bestByRagHit().refusalAccuracy());
    }
}
