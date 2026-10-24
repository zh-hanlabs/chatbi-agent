package com.example.chatbi.chat;

import com.example.chatbi.db.KeyHolderUtil;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.RowMapper;
import org.springframework.jdbc.support.GeneratedKeyHolder;
import org.springframework.jdbc.support.KeyHolder;
import org.springframework.stereotype.Repository;

import java.sql.PreparedStatement;
import java.sql.Statement;
import java.util.List;
import java.util.Optional;

@Repository
public class ConversationRepository {

    private static final RowMapper<Conversation> CONVERSATION_ROW = (rs, rowNum) -> new Conversation(
            rs.getString("id"),
            rs.getLong("user_id"),
            rs.getString("title"),
            rs.getTimestamp("created_at").toLocalDateTime(),
            rs.getTimestamp("updated_at").toLocalDateTime());

    private static final RowMapper<ChatMessage> MESSAGE_ROW = (rs, rowNum) -> new ChatMessage(
            rs.getLong("id"),
            rs.getString("conversation_id"),
            rs.getString("role"),
            rs.getString("content"),
            rs.getString("tool_call_json"),
            rs.getTimestamp("created_at").toLocalDateTime());

    private final JdbcTemplate jdbcTemplate;

    public ConversationRepository(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }

    public boolean userExists(long userId) {
        Integer count = jdbcTemplate.queryForObject("SELECT COUNT(*) FROM users WHERE id = ?", Integer.class, userId);
        return count != null && count > 0;
    }

    public void insert(Conversation conversation) {
        jdbcTemplate.update("INSERT INTO conversations(id, user_id, title) VALUES (?, ?, ?)",
                conversation.id(), conversation.userId(), conversation.title());
    }

    public Optional<Conversation> findById(String id) {
        List<Conversation> found = jdbcTemplate.query(
                "SELECT id, user_id, title, created_at, updated_at FROM conversations WHERE id = ?",
                CONVERSATION_ROW, id);
        return found.stream().findFirst();
    }

    public List<Conversation> findByUserId(long userId) {
        return jdbcTemplate.query(
                "SELECT id, user_id, title, created_at, updated_at FROM conversations WHERE user_id = ? "
                        + "ORDER BY updated_at DESC, id DESC",
                CONVERSATION_ROW, userId);
    }

    public void touchUpdatedAt(String conversationId) {
        jdbcTemplate.update("UPDATE conversations SET updated_at = CURRENT_TIMESTAMP WHERE id = ?", conversationId);
    }

    public long insertMessage(ChatMessage message) {
        KeyHolder keyHolder = new GeneratedKeyHolder();
        jdbcTemplate.update(con -> {
            PreparedStatement ps = con.prepareStatement(
                    "INSERT INTO messages(conversation_id, role, content, tool_call_json) VALUES (?, ?, ?, ?)",
                    Statement.RETURN_GENERATED_KEYS);
            ps.setString(1, message.conversationId());
            ps.setString(2, message.role());
            ps.setString(3, message.content());
            ps.setString(4, message.toolCallJson());
            return ps;
        }, keyHolder);
        return KeyHolderUtil.extractId(keyHolder);
    }

    public List<ChatMessage> findMessages(String conversationId) {
        return jdbcTemplate.query(
                "SELECT id, conversation_id, role, content, tool_call_json, created_at FROM messages "
                        + "WHERE conversation_id = ? ORDER BY created_at, id",
                MESSAGE_ROW, conversationId);
    }
}
