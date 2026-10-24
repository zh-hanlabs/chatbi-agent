-- 评估用例集:NL2SQL 生成 / RAG 知识问答 / 拒答 / SQL 安全校验 四类共 50 条。
-- expected_* 为空表示该项不参与判定;评估口径见 EvaluationService。

CREATE TABLE evaluation_cases (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    category VARCHAR(32) NOT NULL,
    question VARCHAR(255) NOT NULL,
    expected_route VARCHAR(16) NULL,
    expected_metric VARCHAR(32) NULL,
    expected_sql TEXT NULL,
    expected_answer_contains VARCHAR(255) NULL,
    expected_allowed BOOLEAN NULL
);

-- NL2SQL:指标 × 区域 × 时间窗组合(20)
INSERT INTO evaluation_cases(category, question, expected_route, expected_metric) VALUES
  ('NL2SQL', '北京的 GMV', 'NL2SQL', 'GMV'),
  ('NL2SQL', '上海的 GMV 是多少', 'NL2SQL', 'GMV'),
  ('NL2SQL', '广州的 GMV', 'NL2SQL', 'GMV'),
  ('NL2SQL', '全部区域的 GMV', 'NL2SQL', 'GMV'),
  ('NL2SQL', '北京的订单量', 'NL2SQL', 'ORDER_COUNT'),
  ('NL2SQL', '上海的订单量有多少', 'NL2SQL', 'ORDER_COUNT'),
  ('NL2SQL', '广州总共有多少单', 'NL2SQL', 'ORDER_COUNT'),
  ('NL2SQL', '总订单量', 'NL2SQL', 'ORDER_COUNT'),
  ('NL2SQL', '北京的退款率', 'NL2SQL', 'REFUND_RATE'),
  ('NL2SQL', '上海的退款率是多少', 'NL2SQL', 'REFUND_RATE'),
  ('NL2SQL', '广州的退款率', 'NL2SQL', 'REFUND_RATE'),
  ('NL2SQL', '近7天北京的订单量', 'NL2SQL', 'ORDER_COUNT'),
  ('NL2SQL', '近30天上海的订单量', 'NL2SQL', 'ORDER_COUNT'),
  ('NL2SQL', '近7天广州的 GMV', 'NL2SQL', 'GMV'),
  ('NL2SQL', '近14天的 GMV', 'NL2SQL', 'GMV'),
  ('NL2SQL', '近7天北京的退款率', 'NL2SQL', 'REFUND_RATE'),
  ('NL2SQL', '最近30天全部订单数', 'NL2SQL', 'ORDER_COUNT'),
  ('NL2SQL', '近7天的成交金额', 'NL2SQL', 'GMV'),
  ('NL2SQL', '上海近7天销售额', 'NL2SQL', 'GMV'),
  ('NL2SQL', '广州近7天订单数', 'NL2SQL', 'ORDER_COUNT');

-- NL2SQL 精确 SQL 断言(6 条代表性用例)
INSERT INTO evaluation_cases(category, question, expected_route, expected_metric, expected_sql) VALUES
  ('NL2SQL', '北京的 GMV 是多少', 'NL2SQL', 'GMV',
   'SELECT SUM(o.amount) AS gmv FROM orders o JOIN regions r ON r.id = o.region_id WHERE o.status = ''COMPLETED'' AND r.name = ''北京'''),
  ('NL2SQL', '总订单量是多少', 'NL2SQL', 'ORDER_COUNT',
   'SELECT COUNT(*) AS order_count FROM orders o'),
  ('NL2SQL', '上海的退款率是多少呢', 'NL2SQL', 'REFUND_RATE',
   'SELECT SUM(CASE WHEN o.status = ''REFUNDED'' THEN 1 ELSE 0 END) * 1.0 / COUNT(*) AS refund_rate FROM orders o JOIN regions r ON r.id = o.region_id WHERE r.name = ''上海'''),
  ('NL2SQL', '近7天北京的订单量', 'NL2SQL', 'ORDER_COUNT',
   'SELECT COUNT(*) AS order_count FROM orders o JOIN regions r ON r.id = o.region_id WHERE r.name = ''北京'' AND o.created_at >= TIMESTAMPADD(DAY, -7, CURRENT_TIMESTAMP)'),
  ('NL2SQL', '近30天的 GMV 是多少', 'NL2SQL', 'GMV',
   'SELECT SUM(o.amount) AS gmv FROM orders o WHERE o.status = ''COMPLETED'' AND o.created_at >= TIMESTAMPADD(DAY, -30, CURRENT_TIMESTAMP)'),
  ('NL2SQL', '广州的订单量', 'NL2SQL', 'ORDER_COUNT',
   'SELECT COUNT(*) AS order_count FROM orders o JOIN regions r ON r.id = o.region_id WHERE r.name = ''广州''');

-- RAG:知识库问答(15),标准语料见 EvaluationService.ensureCorpus
INSERT INTO evaluation_cases(category, question, expected_route, expected_answer_contains) VALUES
  ('RAG', 'GMV 的口径是什么', 'RAG', '已完成订单的金额总和'),
  ('RAG', 'GMV 口径指的是什么', 'RAG', '已完成订单的金额总和'),
  ('RAG', 'GMV 的定义说明一下', 'RAG', '已完成订单的金额总和'),
  ('RAG', '订单量的口径是什么', 'RAG', '全部状态的订单总数'),
  ('RAG', '订单量口径指的是什么', 'RAG', '全部状态的订单总数'),
  ('RAG', '退款率的口径是什么', 'RAG', '退款订单数除以总订单数'),
  ('RAG', '退款率怎么算', 'RAG', '退款订单数除以总订单数'),
  ('RAG', '退款率的定义', 'RAG', '退款订单数除以总订单数'),
  ('RAG', '北京区域覆盖什么市场', 'RAG', '华北市场'),
  ('RAG', '上海区域的市场说明', 'RAG', '华东市场'),
  ('RAG', '广州区域介绍', 'RAG', '华南市场'),
  ('RAG', '北京区域的市场定义', 'RAG', '华北市场'),
  ('RAG', '订单量的定义是什么', 'RAG', '全部状态的订单总数'),
  ('RAG', 'GMV 口径如何计算', 'RAG', '已完成订单的金额总和'),
  ('RAG', '上海区域覆盖的市场是什么', 'RAG', '华东市场');

-- 拒答:域外问题应明确拒绝(10)
INSERT INTO evaluation_cases(category, question, expected_route) VALUES
  ('REFUSAL', '食堂今天中午有什么菜', 'REFUSED'),
  ('REFUSAL', '明天天气怎么样', 'REFUSED'),
  ('REFUSAL', '世界杯赛程安排', 'REFUSED'),
  ('REFUSAL', '地铁线路怎么坐', 'REFUSED'),
  ('REFUSAL', '年假还有几天', 'REFUSED'),
  ('REFUSAL', '推荐几部电影', 'REFUSED'),
  ('REFUSAL', '旅游攻略哪家好', 'REFUSED'),
  ('REFUSAL', '健身计划怎么做', 'REFUSED'),
  ('REFUSAL', '股票行情如何', 'REFUSED'),
  ('REFUSAL', '编程语言入门选哪个', 'REFUSED');

-- SQL 安全校验(5)
INSERT INTO evaluation_cases(category, question, expected_allowed) VALUES
  ('SQL_GUARD', 'SELECT COUNT(*) AS c FROM orders', TRUE),
  ('SQL_GUARD', 'SELECT SUM(o.amount) AS gmv FROM orders o WHERE o.status = ''COMPLETED''', TRUE),
  ('SQL_GUARD', 'DELETE FROM orders', FALSE),
  ('SQL_GUARD', 'SELECT * FROM orders', FALSE),
  ('SQL_GUARD', 'SELECT customer_phone FROM orders', FALSE);
