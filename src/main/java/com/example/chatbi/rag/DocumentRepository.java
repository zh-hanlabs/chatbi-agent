package com.example.chatbi.rag;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.RowMapper;
import org.springframework.jdbc.support.GeneratedKeyHolder;
import org.springframework.jdbc.support.KeyHolder;
import org.springframework.stereotype.Repository;

import java.sql.PreparedStatement;
import java.sql.Statement;
import java.sql.Timestamp;
import java.util.List;
import java.util.Optional;

@Repository
public class DocumentRepository {

    public record DocumentRow(long id, String title, String content, Timestamp createdAt) {
    }

    public record ChunkRow(long id, long documentId, int chunkIndex, String content, String embedding,
                           Timestamp createdAt) {
    }

    private static final RowMapper<DocumentRow> DOCUMENT_ROW = (rs, rowNum) -> new DocumentRow(
            rs.getLong("id"), rs.getString("title"), rs.getString("content"), rs.getTimestamp("created_at"));

    private static final RowMapper<ChunkRow> CHUNK_ROW = (rs, rowNum) -> new ChunkRow(
            rs.getLong("id"), rs.getLong("document_id"), rs.getInt("chunk_index"), rs.getString("content"),
            rs.getString("embedding"), rs.getTimestamp("created_at"));

    private final JdbcTemplate jdbcTemplate;

    public DocumentRepository(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }

    public long insertDocument(String title, String content) {
        KeyHolder keyHolder = new GeneratedKeyHolder();
        jdbcTemplate.update(con -> {
            PreparedStatement ps = con.prepareStatement(
                    "INSERT INTO documents(title, content) VALUES (?, ?)", Statement.RETURN_GENERATED_KEYS);
            ps.setString(1, title);
            ps.setString(2, content);
            return ps;
        }, keyHolder);
        return keyHolder.getKeys().entrySet().stream()
                .filter(entry -> entry.getKey().equalsIgnoreCase("id"))
                .map(entry -> (Number) entry.getValue())
                .findFirst()
                .orElseThrow(() -> new IllegalStateException("未取到 documents 自增主键"))
                .longValue();
    }

    public void insertChunk(long documentId, int chunkIndex, String content, String embeddingJson) {
        jdbcTemplate.update("INSERT INTO document_chunks(document_id, chunk_index, content, embedding) "
                + "VALUES (?, ?, ?, ?)", documentId, chunkIndex, content, embeddingJson);
    }

    public List<DocumentRow> listDocuments() {
        return jdbcTemplate.query("SELECT id, title, content, created_at FROM documents ORDER BY id DESC",
                DOCUMENT_ROW);
    }

    public Optional<DocumentRow> findDocument(long id) {
        List<DocumentRow> found = jdbcTemplate.query(
                "SELECT id, title, content, created_at FROM documents WHERE id = ?", DOCUMENT_ROW, id);
        return found.stream().findFirst();
    }

    public List<ChunkRow> findChunks(long documentId) {
        return jdbcTemplate.query(
                "SELECT id, document_id, chunk_index, content, embedding, created_at FROM document_chunks "
                        + "WHERE document_id = ? ORDER BY chunk_index", CHUNK_ROW, documentId);
    }

    public List<ChunkRow> allChunks() {
        return jdbcTemplate.query(
                "SELECT id, document_id, chunk_index, content, embedding, created_at FROM document_chunks "
                        + "ORDER BY id", CHUNK_ROW);
    }
}
