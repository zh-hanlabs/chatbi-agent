package com.example.chatbi;

import com.example.chatbi.agent.MetricCatalog;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
@ActiveProfiles("test")
class AgentControllerTests {

    @Autowired
    private MockMvc mockMvc;

    @Test
    void chatAnswersMetricQuestionWithoutTool() throws Exception {
        mockMvc.perform(post("/api/chat")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"question\":\"GMV 的口径是什么\"}"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.answer").value("GMV is the sum of completed order amounts."));
    }

    @Test
    void toolEndpointReturnsFunctionCallingIntent() throws Exception {
        mockMvc.perform(get("/api/tools"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.requiresTool").value(true))
                .andExpect(jsonPath("$.toolCall.name").value("query_gmv"));
    }

    @Test
    void blankQuestionIsRejected() throws Exception {
        mockMvc.perform(post("/api/chat")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"question\":\" \"}"))
                .andExpect(status().isBadRequest());
    }

    @Test
    void metricCatalogIsAvailable() {
        org.assertj.core.api.Assertions.assertThat(MetricCatalog.contains("GMV")).isTrue();
    }
}
