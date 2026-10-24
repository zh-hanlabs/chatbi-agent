package com.example.chatbi.api;

import com.example.chatbi.authz.PermissionService;
import com.example.chatbi.authz.UserPermissions;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/users")
public class UserController {

    private final PermissionService permissionService;

    public UserController(PermissionService permissionService) {
        this.permissionService = permissionService;
    }

    /** 用户数据权限视图:可查区域与指标集合 */
    @GetMapping("/{id}/permissions")
    public ResponseEntity<UserPermissions> permissions(@PathVariable long id) {
        if (!permissionService.userExists(id)) {
            throw new NotFoundException("用户不存在: " + id);
        }
        return ResponseEntity.ok(permissionService.load(id));
    }
}
