package com.example.chatbi.authz;

import com.example.chatbi.api.PermissionDeniedException;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;

import java.util.HashSet;
import java.util.Set;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/**
 * 数据权限裁决:区域与指标两类,来源于 V1 的权限表。
 * 用户不存在视为无任何权限(默认拒绝);管理员不豁免——权限表说了算。
 */
@Service
public class PermissionService {

    private static final Pattern REGION_LITERAL = Pattern.compile(
            "name\\s*=\\s*'([^']+)'", Pattern.CASE_INSENSITIVE);

    private final JdbcTemplate jdbcTemplate;

    public PermissionService(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }

    public boolean userExists(long userId) {
        Integer count = jdbcTemplate.queryForObject("SELECT COUNT(*) FROM users WHERE id = ?",
                Integer.class, userId);
        return count != null && count > 0;
    }

    public UserPermissions load(long userId) {
        Set<String> regions = new HashSet<>(jdbcTemplate.queryForList(
                "SELECT r.name FROM user_region_permissions p JOIN regions r ON r.id = p.region_id "
                        + "WHERE p.user_id = ?", String.class, userId));
        Set<String> metrics = new HashSet<>(jdbcTemplate.queryForList(
                "SELECT metric FROM user_metric_permissions WHERE user_id = ?", String.class, userId));
        return new UserPermissions(userId, regions, metrics);
    }

    /** 生成层裁决:metric 必须在指标权限内;region 非空时必须在区域权限内 */
    public void checkMetricAndRegion(long userId, String metric, String region) {
        UserPermissions permissions = load(userId);
        if (!permissions.metrics().contains(metric)) {
            throw new PermissionDeniedException("无 " + metric + " 指标的查询权限");
        }
        if (region != null && !permissions.regions().contains(region)) {
            throw new PermissionDeniedException("无 " + region + " 区域的查询权限");
        }
    }

    /** confirm 层裁决:提取 SQL 中 r.name='X' 的区域字面量,逐一校验 */
    public void checkRegionsInSql(long userId, String sql) {
        UserPermissions permissions = load(userId);
        Matcher matcher = REGION_LITERAL.matcher(sql);
        while (matcher.find()) {
            String region = matcher.group(1);
            if (!permissions.regions().contains(region)) {
                throw new PermissionDeniedException("无 " + region + " 区域的查询权限");
            }
        }
    }
}
