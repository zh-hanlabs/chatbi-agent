package com.example.chatbi.authz;

import java.util.Set;

/** 用户的区域与指标权限集合;用户不存在时为空集合(默认拒绝) */
public record UserPermissions(long userId, Set<String> regions, Set<String> metrics) {
}
