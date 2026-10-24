package com.example.chatbi.rag;

import com.example.chatbi.api.UnsupportedQuestionException;
import com.example.chatbi.nl2sql.GeneratedSql;
import com.example.chatbi.nl2sql.SqlGenerator;
import org.springframework.stereotype.Service;

import java.util.List;
import java.util.regex.Pattern;

/**
 * 问数路由:先判意图——问口径/定义的知识型问题直接进知识库;
 * 其余能生成 SQL 的指标问题走 NL2SQL;再不行交给知识库检索;
 * 检索低于阈值则拒答。顺序即「先辨意图、再算数、再查文档、都不行就拒答」。
 */
@Service
public class RagRouter {

    public record RoutedAnswer(String route, String answer, GeneratedSql sql,
                               List<RetrievalService.ScoredChunk> citations) {
    }

    public static final String ROUTE_NL2SQL = "NL2SQL";
    public static final String ROUTE_RAG = "RAG";
    public static final String ROUTE_REFUSED = "REFUSED";

    /** 知识型意图信号:问的是概念与口径,不是数据本身 */
    private static final Pattern KNOWLEDGE_INTENT = Pattern.compile(
            "口径|定义|什么意思|是什么|指的是|含义|解释|怎么算|如何计算|说明|介绍");

    private final SqlGenerator sqlGenerator;
    private final RagAnswerService ragAnswerService;

    public RagRouter(SqlGenerator sqlGenerator, RagAnswerService ragAnswerService) {
        this.sqlGenerator = sqlGenerator;
        this.ragAnswerService = ragAnswerService;
    }

    public RoutedAnswer route(String question) {
        if (!isKnowledgeQuestion(question)) {
            try {
                GeneratedSql sql = sqlGenerator.generate(question);
                return new RoutedAnswer(ROUTE_NL2SQL, sql.explanation(), sql, List.of());
            } catch (UnsupportedQuestionException notAMetricQuestion) {
                // 落到知识库
            }
        }
        RagAnswerService.RagAnswer rag = ragAnswerService.answer(question);
        if (rag.refused()) {
            return new RoutedAnswer(ROUTE_REFUSED, rag.answer(), null, List.of());
        }
        return new RoutedAnswer(ROUTE_RAG, rag.answer(), null, rag.citations());
    }

    private boolean isKnowledgeQuestion(String question) {
        return KNOWLEDGE_INTENT.matcher(question).find();
    }
}
