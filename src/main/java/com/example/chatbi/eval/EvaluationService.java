package com.example.chatbi.eval;

import com.example.chatbi.nl2sql.SqlSecurityValidator;
import com.example.chatbi.nl2sql.ValidationResult;
import com.example.chatbi.rag.DocumentIngestionService;
import com.example.chatbi.rag.DocumentRepository;
import com.example.chatbi.rag.RagRouter;
import org.springframework.stereotype.Service;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * 自动评估:遍历 evaluation_cases,逐条跑真实链路(NL2SQL 生成 / RAG 路由 /
 * SQL 安全校验),汇总各类准确率。知识库为空时先灌入标准语料,
 * 保证 RAG 用例可比、可复现。
 */
@Service
public class EvaluationService {

    /** 评估以种子管理员(全权限)身份路由,衡量系统能力而非个别用户权限 */
    private static final long EVAL_USER_ID = 3L;

    public static final String CATEGORY_NL2SQL = "NL2SQL";
    public static final String CATEGORY_RAG = "RAG";
    public static final String CATEGORY_REFUSAL = "REFUSAL";
    public static final String CATEGORY_SQL_GUARD = "SQL_GUARD";

    private static final String STANDARD_CORPUS_TITLE_1 = "【评估标准语料】业务口径说明";
    private static final String STANDARD_CORPUS_TITLE_2 = "【评估标准语料】区域市场说明";

    public record CaseResult(long id, String category, String question, boolean passed, String actual) {
    }

    public record CategoryStat(int total, int passed, double accuracy) {
    }

    public record EvaluationReport(int total, int passed, double accuracy, Map<String, CategoryStat> byCategory,
                                   List<CaseResult> failures) {
    }

    private final EvaluationCaseRepository caseRepository;
    private final RagRouter ragRouter;
    private final SqlSecurityValidator validator;
    private final DocumentRepository documentRepository;
    private final DocumentIngestionService ingestionService;

    public EvaluationService(EvaluationCaseRepository caseRepository, RagRouter ragRouter,
            SqlSecurityValidator validator, DocumentRepository documentRepository,
            DocumentIngestionService ingestionService) {
        this.caseRepository = caseRepository;
        this.ragRouter = ragRouter;
        this.validator = validator;
        this.documentRepository = documentRepository;
        this.ingestionService = ingestionService;
    }

    public EvaluationReport run() {
        ensureCorpus();
        List<CaseResult> results = new ArrayList<>();
        for (EvaluationCaseRepository.EvalCase evalCase : caseRepository.findAll()) {
            results.add(evaluate(evalCase));
        }

        int total = results.size();
        int passed = (int) results.stream().filter(CaseResult::passed).count();
        Map<String, CategoryStat> byCategory = new LinkedHashMap<>();
        for (String category : List.of(CATEGORY_NL2SQL, CATEGORY_RAG, CATEGORY_REFUSAL, CATEGORY_SQL_GUARD)) {
            List<CaseResult> ofCategory = results.stream().filter(r -> r.category().equals(category)).toList();
            if (ofCategory.isEmpty()) {
                continue;
            }
            int categoryPassed = (int) ofCategory.stream().filter(CaseResult::passed).count();
            byCategory.put(category, new CategoryStat(ofCategory.size(), categoryPassed,
                    ofCategory.size() == 0 ? 0 : (double) categoryPassed / ofCategory.size()));
        }
        return new EvaluationReport(total, passed, total == 0 ? 0 : (double) passed / total, byCategory,
                results.stream().filter(r -> !r.passed()).toList());
    }

    private CaseResult evaluate(EvaluationCaseRepository.EvalCase evalCase) {
        return switch (evalCase.category()) {
            case CATEGORY_NL2SQL -> evaluateNl2sql(evalCase);
            case CATEGORY_RAG -> evaluateRag(evalCase);
            case CATEGORY_REFUSAL -> evaluateRefusal(evalCase);
            case CATEGORY_SQL_GUARD -> evaluateGuard(evalCase);
            default -> new CaseResult(evalCase.id(), evalCase.category(), evalCase.question(), false,
                    "未知类别: " + evalCase.category());
        };
    }

    private CaseResult evaluateNl2sql(EvaluationCaseRepository.EvalCase evalCase) {
        RagRouter.RoutedAnswer routed = ragRouter.route(EVAL_USER_ID, evalCase.question());
        boolean passed = RagRouter.ROUTE_NL2SQL.equals(routed.route())
                && (evalCase.expectedMetric() == null || evalCase.expectedMetric().equals(routed.sql() == null
                        ? null : routed.sql().metric()))
                && (evalCase.expectedSql() == null || evalCase.expectedSql().equals(routed.sql() == null
                        ? null : routed.sql().sql()));
        String actual = "route=" + routed.route() + ", sql=" + (routed.sql() == null ? null : routed.sql().sql());
        return new CaseResult(evalCase.id(), evalCase.category(), evalCase.question(), passed, actual);
    }

    private CaseResult evaluateRag(EvaluationCaseRepository.EvalCase evalCase) {
        RagRouter.RoutedAnswer routed = ragRouter.route(EVAL_USER_ID, evalCase.question());
        boolean passed = RagRouter.ROUTE_RAG.equals(routed.route())
                && (evalCase.expectedAnswerContains() == null
                        || routed.answer().contains(evalCase.expectedAnswerContains()));
        String actual = "route=" + routed.route() + ", answer=" + routed.answer();
        return new CaseResult(evalCase.id(), evalCase.category(), evalCase.question(), passed, actual);
    }

    private CaseResult evaluateRefusal(EvaluationCaseRepository.EvalCase evalCase) {
        RagRouter.RoutedAnswer routed = ragRouter.route(EVAL_USER_ID, evalCase.question());
        boolean passed = RagRouter.ROUTE_REFUSED.equals(routed.route());
        return new CaseResult(evalCase.id(), evalCase.category(), evalCase.question(), passed,
                "route=" + routed.route());
    }

    private CaseResult evaluateGuard(EvaluationCaseRepository.EvalCase evalCase) {
        ValidationResult verdict = validator.validate(evalCase.question());
        boolean passed = verdict.allowed() == evalCase.expectedAllowed();
        return new CaseResult(evalCase.id(), evalCase.category(), evalCase.question(), passed,
                "allowed=" + verdict.allowed() + ", reason=" + verdict.reason());
    }

    /** RAG 用例依赖标准语料;用专属标题做幂等检查,知识库有无关文档也照常补齐 */
    private void ensureCorpus() {
        var titles = documentRepository.listDocuments().stream()
                .map(DocumentRepository.DocumentRow::title)
                .collect(java.util.stream.Collectors.toSet());
        if (!titles.contains(STANDARD_CORPUS_TITLE_1)) {
            ingestionService.ingest(STANDARD_CORPUS_TITLE_1,
                    "GMV 的口径是已完成订单的金额总和。\n\n订单量的口径是全部状态的订单总数。\n\n"
                            + "退款率的口径是退款订单数除以总订单数。");
        }
        if (!titles.contains(STANDARD_CORPUS_TITLE_2)) {
            ingestionService.ingest(STANDARD_CORPUS_TITLE_2,
                    "北京区域覆盖华北市场,客单价较高。\n\n上海区域覆盖华东市场,复购率最高。\n\n"
                            + "广州区域覆盖华南市场,新客占比最高。");
        }
    }
}
