INSERT INTO regions(id, name) VALUES
  (1, '北京'),
  (2, '上海'),
  (3, '广州');

INSERT INTO products(id, sku, name, category) VALUES
  (1, 'SKU-1001', '机械键盘', '数码配件'),
  (2, 'SKU-1002', '无线耳机', '数码配件'),
  (3, 'SKU-1003', '显示器', '电脑办公');

INSERT INTO users(id, username, display_name, role) VALUES
  (1, 'analyst-bj', '北京分析师', 'ANALYST'),
  (2, 'analyst-sh', '上海分析师', 'ANALYST'),
  (3, 'admin', '管理员', 'ADMIN');

INSERT INTO user_region_permissions(user_id, region_id) VALUES
  (1, 1), (2, 2), (3, 1), (3, 2), (3, 3);

INSERT INTO user_metric_permissions(user_id, metric) VALUES
  (1, 'GMV'), (1, 'ORDER_COUNT'),
  (2, 'GMV'), (2, 'REFUND_RATE'),
  (3, 'GMV'), (3, 'ORDER_COUNT'), (3, 'REFUND_RATE');

INSERT INTO orders(order_no, region_id, product_id, customer_phone, amount, status, created_at) VALUES
  ('NO-2026-001', 1, 1, '13800000001', 399.00, 'COMPLETED', '2026-10-01 10:00:00'),
  ('NO-2026-002', 1, 2, '13800000002', 699.00, 'COMPLETED', '2026-10-02 11:00:00'),
  ('NO-2026-003', 2, 3, '13800000003', 1799.00, 'COMPLETED', '2026-10-03 12:00:00'),
  ('NO-2026-004', 2, 1, '13800000004', 499.00, 'REFUNDED', '2026-10-04 13:00:00'),
  ('NO-2026-005', 3, 2, '13800000005', 899.00, 'COMPLETED', '2026-10-05 14:00:00');
