/**
 * @repo: https://github.com/xiaotuolu/DevSupport-AI
 */
import { useEffect, useState } from "react";
import { Card, Table, Tag, Row, Col, Descriptions, Select, Button, Space, message, Typography, Divider, Input } from "antd";
import { wbTickets, wbTicketDetail, wbUpdateTicket, getTrace, wbSuggestReply, wbReply } from "../api";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import TraceFlow from "../components/TraceFlow";
import Highlight from "../components/Highlight";
import DiagnosisCard from "../components/DiagnosisCard";

const PRIORITY_COLOR: Record<string, string> = { P0: "red", P1: "volcano", P2: "blue", P3: "default" };
const STATUSES = ["new", "processing", "waiting_customer", "resolved", "closed", "escalated"];

export default function Workbench() {
  const [tickets, setTickets] = useState<any[]>([]);
  const [filter, setFilter] = useState<any>({});
  const [detail, setDetail] = useState<any>(null);
  const [trace, setTrace] = useState<any>(null);
  const [reply, setReply] = useState("");
  const [suggesting, setSuggesting] = useState(false);

  const load = () => wbTickets(filter).then((d) => setTickets(d.tickets));
  useEffect(() => { load(); }, [JSON.stringify(filter)]);

  const open = async (id: string) => {
    try {
      const d = await wbTicketDetail(id);
      setDetail(d);
      setTrace(null);
      // 取会话里最后一条带 trace_id 的消息，加载其 Agent 链路用于可视化
      const traceId = d.conversation_messages
        ?.map((m: any) => m.meta?.trace_id)
        .filter(Boolean)
        .pop();
      if (traceId) {
        try { setTrace(await getTrace(traceId)); } catch { /* trace 可能不存在 */ }
      }
    } catch (e: any) {
      message.error(`打开工单失败：${e?.response?.status === 401 ? "登录已过期，请重新登录" : "后端服务不可用，请确认服务已启动"}`);
    }
  };

  const setStatus = async (status: string) => {
    await wbUpdateTicket(detail.ticket.ticket_id, { status });
    message.success(`状态更新为 ${status}`);
    load();
    open(detail.ticket.ticket_id);
  };

  const suggest = async () => {
    setSuggesting(true);
    try {
      const r = await wbSuggestReply(detail.ticket.conversation_id);
      setReply(r.suggestion);
    } catch {
      message.error("生成失败");
    } finally {
      setSuggesting(false);
    }
  };

  const sendReply = async () => {
    if (!reply.trim()) return;
    await wbReply(detail.ticket.conversation_id, reply.trim());
    message.success("已回复客户（客户可在「我的会话」看到）");
    setReply("");
    open(detail.ticket.ticket_id);
  };

  // 列表视图：占满整页
  if (!detail) {
    return (
      <Card
        title="工单列表"
        extra={
          <Space>
            <Select allowClear placeholder="状态" style={{ width: 140 }}
              options={STATUSES.map((s) => ({ value: s, label: s }))}
              onChange={(v) => setFilter({ ...filter, status: v })} />
            <Select allowClear placeholder="优先级" style={{ width: 100 }}
              options={["P0", "P1", "P2", "P3"].map((s) => ({ value: s, label: s }))}
              onChange={(v) => setFilter({ ...filter, priority: v })} />
            <Button onClick={load}>刷新</Button>
          </Space>
        }
      >
        <Typography.Text type="secondary" style={{ display: "block", marginBottom: 12 }}>
          点击任意工单行，查看工单详情、Agent 链路与人工回复。
        </Typography.Text>
        <Table
          rowKey="ticket_id"
          dataSource={tickets}
          pagination={{ pageSize: 12 }}
          onRow={(r) => ({ onClick: () => open(r.ticket_id), style: { cursor: "pointer" } })}
          columns={[
            { title: "工单号", dataIndex: "ticket_id" },
            { title: "标题", dataIndex: "title", ellipsis: true },
            { title: "类型", dataIndex: "category", width: 100 },
            { title: "租户", dataIndex: "tenant_id", width: 110 },
            { title: "优先级", dataIndex: "priority", width: 90, render: (p) => <Tag color={PRIORITY_COLOR[p]}>{p}</Tag> },
            { title: "状态", dataIndex: "status", width: 130, render: (s) => <Tag>{s}</Tag> },
            { title: "创建时间", dataIndex: "created_at", width: 170, render: (t) => t?.replace("T", " ").slice(0, 19) },
            { title: "", width: 70, render: () => <a>详情 ›</a> },
          ]}
        />
      </Card>
    );
  }

  // 详情视图：占满整页 + 返回按钮
  return (
    <Row gutter={12}>
      <Col span={24}>
        {detail ? (
          <Card
            title={
              <Space>
                <Button onClick={() => { setDetail(null); load(); }}>← 返回工单列表</Button>
                <span>工单详情 · {detail.ticket.ticket_id}</span>
              </Space>
            }
            extra={
              <Space wrap>
                <Button size="small" onClick={() => open(detail.ticket.ticket_id)}>刷新</Button>
                {STATUSES.map((s) => (
                  <Button key={s} size="small" type={detail.ticket.status === s ? "primary" : "default"} onClick={() => setStatus(s)}>{s}</Button>
                ))}
              </Space>
            }>
            <Descriptions column={2} size="small" bordered>
              <Descriptions.Item label="标题" span={2}>{detail.ticket.title}</Descriptions.Item>
              <Descriptions.Item label="类型">{detail.ticket.category}</Descriptions.Item>
              <Descriptions.Item label="优先级"><Tag color={PRIORITY_COLOR[detail.ticket.priority]}>{detail.ticket.priority}</Tag></Descriptions.Item>
              <Descriptions.Item label="错误码">{detail.ticket.error_code || "-"}</Descriptions.Item>
              <Descriptions.Item label="关联接口">{detail.ticket.related_endpoint || "-"}</Descriptions.Item>
              <Descriptions.Item label="AI 诊断" span={2}>
                <div className="md" style={{ maxHeight: 200, overflow: "auto" }}>
                  {detail.ticket.ai_diagnosis ? <ReactMarkdown remarkPlugins={[remarkGfm]}>{detail.ticket.ai_diagnosis}</ReactMarkdown> : "-"}
                </div>
              </Descriptions.Item>
            </Descriptions>

            <Divider orientation="left" plain>Agent 链路</Divider>
            {trace ? (
              <>
                <Typography.Text type="secondary">
                  trace {trace.trace_id} · 总耗时 {trace.total_duration_ms}ms · {trace.total_tokens} tokens
                </Typography.Text>
                <TraceFlow steps={trace.steps} />
              </>
            ) : (
              <Typography.Text type="secondary">该工单暂无关联链路</Typography.Text>
            )}

            {detail.conversation_messages?.length > 0 && (
              <>
                <Divider orientation="left" plain>对话记录（含客户最新消息）</Divider>
                <div style={{ maxHeight: 240, overflow: "auto", padding: 4 }}>
                  {detail.conversation_messages.map((m: any, i: number) => (
                    <div key={i} style={{ display: "flex", flexDirection: m.role === "user" ? "row-reverse" : "row", margin: "6px 0" }}>
                      <div style={{ maxWidth: "82%", padding: "6px 10px", borderRadius: 6, background: m.role === "user" ? "#e6f4ff" : "#f6ffed", fontSize: 13 }}>
                        {m.meta?.card ? (
                          <DiagnosisCard card={m.meta.card} />
                        ) : m.role === "user" ? (
                          <Highlight text={m.content} />
                        ) : (
                          <div className="md"><ReactMarkdown remarkPlugins={[remarkGfm]}>{m.content}</ReactMarkdown></div>
                        )}
                        {m.meta?.by === "human" && <Tag color="purple" style={{ marginLeft: 6 }}>人工·{m.meta.agent_name}</Tag>}
                        {m.role === "assistant" && m.meta?.by !== "human" && <Tag color="green" style={{ marginLeft: 6 }}>🤖 AI</Tag>}
                      </div>
                    </div>
                  ))}
                </div>
              </>
            )}

            {detail.ticket.conversation_id && (
              <>
                <Divider orientation="left" plain>人工回复客户</Divider>
                <Space style={{ marginBottom: 8 }}>
                  <Button size="small" loading={suggesting} onClick={suggest}>✨ 生成 AI 建议回复</Button>
                  <Typography.Text type="secondary" style={{ fontSize: 12 }}>可编辑后发送</Typography.Text>
                </Space>
                <Input.TextArea
                  value={reply}
                  onChange={(e) => setReply(e.target.value)}
                  autoSize={{ minRows: 3, maxRows: 8 }}
                  placeholder="编辑回复内容，发送后客户可在「我的会话」中看到"
                />
                <Button type="primary" size="small" style={{ marginTop: 8 }} onClick={sendReply}>发送回复给客户</Button>
              </>
            )}
          </Card>
        ) : null}
      </Col>
    </Row>
  );
}
