CREATE TABLE documents (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    title VARCHAR(200) NOT NULL,
    content TEXT NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- embedding 存 JSON 数组文本,MySQL 与 H2 通用;规模为演示级,相似度在应用层计算
CREATE TABLE document_chunks (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    document_id BIGINT NOT NULL,
    chunk_index INT NOT NULL,
    content TEXT NOT NULL,
    embedding TEXT NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_chunk_document FOREIGN KEY (document_id) REFERENCES documents(id),
    CONSTRAINT uq_chunk_document_index UNIQUE (document_id, chunk_index)
);

CREATE INDEX idx_chunks_document ON document_chunks(document_id);
