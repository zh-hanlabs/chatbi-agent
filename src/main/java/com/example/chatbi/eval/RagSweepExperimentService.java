package com.example.chatbi.eval;

import com.example.chatbi.rag.EmbeddingClient;
import com.example.chatbi.rag.TextChunker;
import com.example.chatbi.rag.VectorMath;
import org.springframework.stereotype.Service;

import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;

/**
 * RAG 参数对比实验:chunk 尺寸 × TopK × 相似度阈值 三轴扫参,
 * 在标准语料与评估用例上离线复算命中率,不依赖运行中的库表。
 * 用于回答「检索参数怎么选」这类问题,结论落 docs/experiments。
 */
@Service
public class RagSweepExperimentService {

    public record SweepConfig(int chunkSize, int overlap, int topK, double minScore) {
    }

    public record SweepRow(SweepConfig config, int ragCases, int ragHits, double ragHitRate,
                           int refusalCases, int refusalsCorrect, double refusalAccuracy) {
    }

    public record SweepReport(int configs, List<SweepRow> rows, SweepRow bestByRagHit) {
    }

    /** 实验语料:两篇短口径文档 + 一篇长运营手册,保证 chunk 尺寸轴有区分度 */
    private static final List<String> CORPUS = List.of(
            "GMV 的口径是已完成订单的金额总和。\n\n订单量的口径是全部状态的订单总数。\n\n"
                    + "退款率的口径是退款订单数除以总订单数。",
            "北京区域覆盖华北市场,客单价较高。\n\n上海区域覆盖华东市场,复购率最高。\n\n"
                    + "广州区域覆盖华南市场,新客占比最高。",
            longManual());

    private final EvaluationCaseRepository caseRepository;
    private final EmbeddingClient embeddingClient;

    public RagSweepExperimentService(EvaluationCaseRepository caseRepository, EmbeddingClient embeddingClient) {
        this.caseRepository = caseRepository;
        this.embeddingClient = embeddingClient;
    }

    public SweepReport run() {
        List<EvaluationCaseRepository.EvalCase> ragCases = casesOf("RAG");
        List<EvaluationCaseRepository.EvalCase> refusalCases = casesOf("REFUSAL");

        List<SweepRow> rows = new ArrayList<>();
        for (int chunkSize : List.of(300, 500, 800)) {
            // 每个 chunk 配置只切块+向量化一次
            TextChunker chunker = new TextChunker(chunkSize, 50);
            List<float[]> chunkVectors = new ArrayList<>();
            List<String> chunkTexts = new ArrayList<>();
            for (String doc : CORPUS) {
                for (String chunk : chunker.chunk(doc)) {
                    chunkTexts.add(chunk);
                    chunkVectors.add(embeddingClient.embed(chunk));
                }
            }

            for (int topK : List.of(1, 3)) {
                for (double minScore : List.of(0.1, 0.2, 0.3)) {
                    rows.add(evaluate(new SweepConfig(chunkSize, 50, topK, minScore),
                            chunkTexts, chunkVectors, ragCases, refusalCases));
                }
            }
        }
        SweepRow best = rows.stream()
                .max(Comparator.comparingDouble(SweepRow::ragHitRate)
                        .thenComparingDouble(SweepRow::refusalAccuracy))
                .orElseThrow();
        return new SweepReport(rows.size(), rows, best);
    }

    private SweepRow evaluate(SweepConfig config, List<String> chunkTexts, List<float[]> chunkVectors,
            List<EvaluationCaseRepository.EvalCase> ragCases,
            List<EvaluationCaseRepository.EvalCase> refusalCases) {
        int ragHits = 0;
        for (EvaluationCaseRepository.EvalCase evalCase : ragCases) {
            List<String> topChunks = topChunks(evalCase.question(), chunkTexts, chunkVectors, config);
            // recall@K:期望内容落在 TopK 任一块即命中
            if (topChunks.stream().anyMatch(text -> text.contains(evalCase.expectedAnswerContains()))) {
                ragHits++;
            }
        }
        int refusalsCorrect = 0;
        for (EvaluationCaseRepository.EvalCase evalCase : refusalCases) {
            List<String> topChunks = topChunks(evalCase.question(), chunkTexts, chunkVectors, config);
            if (topChunks.isEmpty()) {
                refusalsCorrect++;
            }
        }
        return new SweepRow(config, ragCases.size(), ragHits,
                ragCases.isEmpty() ? 0 : (double) ragHits / ragCases.size(),
                refusalCases.size(), refusalsCorrect,
                refusalCases.isEmpty() ? 0 : (double) refusalsCorrect / refusalCases.size());
    }

    /** 得分过阈值的块按相似度取 TopK;全部低于阈值返回空(视为应拒答) */
    private List<String> topChunks(String question, List<String> chunkTexts, List<float[]> chunkVectors,
            SweepConfig config) {
        float[] queryVector = embeddingClient.embed(question);
        record Scored(double score, String text) {
        }
        return java.util.stream.IntStream.range(0, chunkVectors.size())
                .mapToObj(i -> new Scored(VectorMath.cosine(queryVector, chunkVectors.get(i)), chunkTexts.get(i)))
                .filter(scored -> scored.score() >= config.minScore())
                .sorted(java.util.Comparator.comparingDouble(Scored::score).reversed())
                .limit(config.topK())
                .map(Scored::text)
                .toList();
    }

    private List<EvaluationCaseRepository.EvalCase> casesOf(String category) {
        return caseRepository.findAll().stream().filter(c -> c.category().equals(category)).toList();
    }

    private static String longManual() {
        StringBuilder manual = new StringBuilder();
        String[] sections = {
                "订单履约流程:订单创建后进入 CREATED 状态,支付完成转为 COMPLETED,退款审核通过转为 REFUNDED。",
                "库存管理原则:畅销品类保持四周安全库存,长尾品类按订单触发补货,避免资金占用。",
                "客服响应要求:工作时段首响不超过十分钟,退款类工单二十四小时内给出结论。",
                "数据报送节奏:每日凌晨同步前一日订单明细,每周一输出区域经营周报,每月初复盘月度目标。",
                "风控红线:单笔金额超过一万元的订单需要人工复核,同 IP 高频下单触发风控拦截。"
        };
        for (int round = 0; round < 4; round++) {
            for (String section : sections) {
                manual.append(section).append("\n\n");
            }
        }
        return manual.toString();
    }
}
