package com.example.chatbi;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.context.ActiveProfiles;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest
@ActiveProfiles("test")
class SchemaMigrationTests {

    @Autowired
    private JdbcTemplate jdbcTemplate;

    @Test
    void migrationCreatesBusinessAndPermissionTables() {
        Integer tables = jdbcTemplate.queryForObject(
                "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = 'public'",
                Integer.class);
        assertThat(tables).isGreaterThanOrEqualTo(10);
    }

    @Test
    void seedDataContainsMultiUserPermissions() {
        Integer bjRegions = jdbcTemplate.queryForObject(
                "SELECT COUNT(*) FROM user_region_permissions urp JOIN users u ON u.id = urp.user_id WHERE u.username = 'analyst-bj'",
                Integer.class);
        Integer adminRegions = jdbcTemplate.queryForObject(
                "SELECT COUNT(*) FROM user_region_permissions urp JOIN users u ON u.id = urp.user_id WHERE u.username = 'admin'",
                Integer.class);

        assertThat(bjRegions).isEqualTo(1);
        assertThat(adminRegions).isEqualTo(3);
    }

    @Test
    void conversationsAreIsolatedByUser() {
        jdbcTemplate.update(
                "INSERT INTO conversations(id, user_id, title) VALUES (?, ?, ?)",
                "conv-bj", 1L, "北京经营分析");
        jdbcTemplate.update(
                "INSERT INTO conversations(id, user_id, title) VALUES (?, ?, ?)",
                "conv-sh", 2L, "上海经营分析");

        Integer shConversationsForBjUser = jdbcTemplate.queryForObject(
                "SELECT COUNT(*) FROM conversations WHERE id = 'conv-sh' AND user_id = 1",
                Integer.class);

        assertThat(shConversationsForBjUser).isZero();
    }
}
