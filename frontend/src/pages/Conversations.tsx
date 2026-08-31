/**
 * @repo: https://github.com/xiaotuolu/DevSupport-AI
 */
import { useEffect, useState } from "react";
import { Card, Row, Col, List, Tag, Typography, Empty, Input, Button, Space, message } from "antd";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { listConversations, getConversation, sendCustomerMessage } from "../api";
import DiagnosisCard from "../components/DiagnosisCard";
import Highlight from "../components/Highlight";

export default function Conversations() {
  const [convs, setConvs] = useState<any[]>([]);
  const [detail, setDetail] = useState<any>(null);
  const [reply, setReply] = useState("");
  const [sending, setSending] = useState(false);

  const refreshList = () => listConversations().then((d) => setConvs(d.conversations));
  useEffect(() => { refreshList(); }, []);

  const open = (id: string) => getConversation(id).then(setDetail);

  const send = async () => {
    if (!reply.trim() || !detail) return;
    setSending(true);
    try {
      await sendCustomerMessage(detail.conversation.id, reply.trim());
      setReply("");
      await open(detail.conversation.id);
      message.success("已发送，技术支持会尽快回复");
    } finally {
      setSending(false);
    }
  };

  // 仅转人工的会话才显示补充输入框（客户消息直达技术支持，不再走 AI）
  const transferred = detail?.conversation?.transferred_to_human;

  return (
    <Row gutter={12} style={{ maxWidth: 1100, margin: "0 auto" }}>
      <Col span={9}>
        <Card title="我的会话" size="small" extra={<Button size="small" onClick={refreshList}>刷新</Button>}>
          <List
            dataSource={convs}
            locale={{ emptyText: <Empty description="暂无会话" /> }}
            renderItem={(c) => (
              <List.Item style={{ cursor: "pointer" }} onClick={() => open(c.id)}>
                <List.Item.Meta
                  title={<>{c.latest_intent || "会话"} {c.transferred_to_human && <Tag color="volcano">已转人工</Tag>}</>}
                  description={`${c.id} · ${c.updated_at?.replace("T", " ").slice(0, 16)}`}
                />
                {c.satisfaction && <Tag color={c.satisfaction === "resolved" ? "green" : "red"}>{c.satisfaction}</Tag>}
              </List.Item>
            )}
          />
        </Card>
      </Col>
      <Col span={15}>
        <Card
          title="会话详情"
          size="small"
          style={{ minHeight: "70vh" }}
          extra={detail && <Button size="small" onClick={() => open(detail.conversation.id)}>刷新</Button>}
        >
          {detail ? (
            <>
              {transferred && (
                <Tag color="volcano" style={{ marginBottom: 8 }}>人工模式 · 你的消息将直达技术支持</Tag>
              )}
              {detail.messages.map((m: any, i: number) => (
                <div key={i} style={{ display: "flex", flexDirection: m.role === "user" ? "row-reverse" : "row", margin: "10px 0" }}>
                  <Card size="small" style={{ maxWidth: "85%", background: m.role === "user" ? "#e6f4ff" : "#fff" }}>
                    {m.meta?.card ? (
                      <DiagnosisCard card={m.meta.card} />
                    ) : m.role === "user" ? (
                      <span style={{ whiteSpace: "pre-wrap" }}><Highlight text={m.content} /></span>
                    ) : (
                      <div className="md"><ReactMarkdown remarkPlugins={[remarkGfm]}>{m.content}</ReactMarkdown></div>
                    )}
                    {m.meta?.by === "human" && <Tag color="purple" style={{ marginTop: 6 }}>人工 · {m.meta.agent_name}</Tag>}
                    {m.role === "assistant" && m.meta?.by !== "human" && <Tag color="green" style={{ marginTop: 6 }}>🤖 AI 助手</Tag>}
                  </Card>
                </div>
              ))}
              {transferred && (
                <Space.Compact style={{ width: "100%", marginTop: 12 }}>
                  <Input.TextArea
                    value={reply}
                    onChange={(e) => setReply(e.target.value)}
                    autoSize={{ minRows: 1, maxRows: 4 }}
                    placeholder="向技术支持补充信息…"
                    onPressEnter={(e) => { e.preventDefault(); send(); }}
                  />
                  <Button type="primary" loading={sending} onClick={send}>发送</Button>
                </Space.Compact>
              )}
            </>
          ) : (
            <Typography.Text type="secondary">点击左侧会话查看历史消息</Typography.Text>
          )}
        </Card>
      </Col>
    </Row>
  );
}
