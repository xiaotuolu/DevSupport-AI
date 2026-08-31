/**
 * @repo: https://github.com/xiaotuolu/DevSupport-AI
 */
import { useEffect, useState } from "react";
import { Card, Row, Col, Statistic, Table, Button, message, Descriptions, Spin } from "antd";
import api, { getMetrics } from "../api";

export default function Metrics() {
  const [m, setM] = useState<any>(null);
  const [evalResult, setEvalResult] = useState<any>(null);
  const [evaluating, setEvaluating] = useState(false);

  useEffect(() => { getMetrics().then(setM); }, []);

  const runEval = async () => {
    setEvaluating(true);
    try {
      const { data } = await api.post("/eval/run");
      setEvalResult(data);
      message.success("评估完成");
    } catch {
      message.error("评估失败");
    } finally {
      setEvaluating(false);
    }
  };

  if (!m) return <Spin />;
  const conv = m.conversations;
  return (
    <div style={{ maxWidth: 1100, margin: "0 auto" }}>
      <Row gutter={12}>
        <Col span={6}><Card><Statistic title="会话总数" value={conv.total} /></Card></Col>
        <Col span={6}><Card><Statistic title="AI 解决率" value={(conv.ai_resolution_rate * 100).toFixed(1)} suffix="%" /></Card></Col>
        <Col span={6}><Card><Statistic title="转人工" value={conv.transferred_to_human} /></Card></Col>
        <Col span={6}><Card><Statistic title="AI 已解决" value={conv.resolved_by_ai} /></Card></Col>
      </Row>

      <Row gutter={12} style={{ marginTop: 12 }}>
        <Col span={12}>
          <Card title="意图分布" size="small">
            <Table rowKey="k" size="small" pagination={false}
              dataSource={Object.entries(m.intent_distribution).map(([k, v]) => ({ k, v }))}
              columns={[{ title: "意图", dataIndex: "k" }, { title: "数量", dataIndex: "v" }]} />
          </Card>
        </Col>
        <Col span={12}>
          <Card title="Token 成本（按租户）" size="small">
            <Table rowKey="tenant_id" size="small" pagination={false}
              dataSource={m.token_cost_by_tenant}
              columns={[
                { title: "租户", dataIndex: "tenant_id" },
                { title: "对话轮次", dataIndex: "turns" },
                { title: "总 Token", dataIndex: "total_tokens" },
              ]} />
          </Card>
        </Col>
      </Row>

      <Card title="质量评估" size="small" style={{ marginTop: 12 }}
        extra={<Button type="primary" loading={evaluating} onClick={runEval}>运行评估集</Button>}>
        {evalResult ? (
          <Descriptions column={3} size="small" bordered>
            <Descriptions.Item label="样本数">{evalResult.total_cases}</Descriptions.Item>
            <Descriptions.Item label="意图准确率">{evalResult.intent_accuracy}</Descriptions.Item>
            <Descriptions.Item label="实体准确率">{evalResult.entity_accuracy}</Descriptions.Item>
            <Descriptions.Item label="引用率">{evalResult.citation_rate}</Descriptions.Item>
            <Descriptions.Item label="转人工准确率">{evalResult.human_transfer_accuracy}</Descriptions.Item>
            <Descriptions.Item label="澄清准确率">{evalResult.clarify_accuracy}</Descriptions.Item>
            <Descriptions.Item label="脱敏准确率">{evalResult.desensitization_accuracy}</Descriptions.Item>
            <Descriptions.Item label="Badcase 数">{evalResult.badcases?.length ?? 0}</Descriptions.Item>
          </Descriptions>
        ) : (
          <span style={{ color: "#888" }}>点击「运行评估集」对标准问题集真实跑分（耗时约 1-2 分钟）</span>
        )}
      </Card>
    </div>
  );
}
