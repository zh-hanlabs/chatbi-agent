CREATE TABLE regions (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(64) NOT NULL UNIQUE
);

CREATE TABLE products (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    sku VARCHAR(64) NOT NULL UNIQUE,
    name VARCHAR(128) NOT NULL,
    category VARCHAR(64) NOT NULL
);

CREATE TABLE orders (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    order_no VARCHAR(64) NOT NULL UNIQUE,
    region_id BIGINT NOT NULL,
    product_id BIGINT NOT NULL,
    customer_phone VARCHAR(32) NOT NULL,
    amount DECIMAL(12, 2) NOT NULL,
    status VARCHAR(32) NOT NULL,
    created_at TIMESTAMP NOT NULL,
    CONSTRAINT fk_orders_region FOREIGN KEY (region_id) REFERENCES regions(id),
    CONSTRAINT fk_orders_product FOREIGN KEY (product_id) REFERENCES products(id),
    CONSTRAINT ck_orders_status CHECK (status IN ('CREATED', 'COMPLETED', 'REFUNDED'))
);

CREATE INDEX idx_orders_region_created_at ON orders(region_id, created_at);
CREATE INDEX idx_orders_status_created_at ON orders(status, created_at);

CREATE TABLE users (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    username VARCHAR(64) NOT NULL UNIQUE,
    display_name VARCHAR(64) NOT NULL,
    role VARCHAR(32) NOT NULL,
    CONSTRAINT ck_users_role CHECK (role IN ('ANALYST', 'ADMIN'))
);

CREATE TABLE user_region_permissions (
    user_id BIGINT NOT NULL,
    region_id BIGINT NOT NULL,
    PRIMARY KEY (user_id, region_id),
    CONSTRAINT fk_region_permission_user FOREIGN KEY (user_id) REFERENCES users(id),
    CONSTRAINT fk_region_permission_region FOREIGN KEY (region_id) REFERENCES regions(id)
);

CREATE TABLE user_metric_permissions (
    user_id BIGINT NOT NULL,
    metric VARCHAR(32) NOT NULL,
    PRIMARY KEY (user_id, metric),
    CONSTRAINT fk_metric_permission_user FOREIGN KEY (user_id) REFERENCES users(id),
    CONSTRAINT ck_metric_permission_metric CHECK (metric IN ('GMV', 'ORDER_COUNT', 'REFUND_RATE'))
);

CREATE TABLE conversations (
    id VARCHAR(36) PRIMARY KEY,
    user_id BIGINT NOT NULL,
    title VARCHAR(128) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_conversation_user FOREIGN KEY (user_id) REFERENCES users(id)
);

CREATE INDEX idx_conversations_user_updated ON conversations(user_id, updated_at);

CREATE TABLE messages (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    conversation_id VARCHAR(36) NOT NULL,
    role VARCHAR(16) NOT NULL,
    content TEXT NOT NULL,
    tool_call_json TEXT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_message_conversation FOREIGN KEY (conversation_id) REFERENCES conversations(id),
    CONSTRAINT ck_message_role CHECK (role IN ('USER', 'ASSISTANT', 'TOOL'))
);

CREATE INDEX idx_messages_conversation_created ON messages(conversation_id, created_at);

CREATE TABLE audit_logs (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    user_id BIGINT NOT NULL,
    conversation_id VARCHAR(36) NULL,
    action VARCHAR(64) NOT NULL,
    question TEXT NULL,
    generated_sql TEXT NULL,
    allowed BOOLEAN NOT NULL,
    reason VARCHAR(255) NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_audit_user FOREIGN KEY (user_id) REFERENCES users(id)
);

CREATE INDEX idx_audit_logs_user_created ON audit_logs(user_id, created_at);
