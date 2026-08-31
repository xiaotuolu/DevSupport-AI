/**
 * @repo: https://github.com/xiaotuolu/DevSupport-AI
 */
import { useRef, useState } from "react";
import { Card, Input, Button, Tag, Space, Typography, Avatar, message as antMsg } from "antd";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { chatStream, submitFeedback } from "../api";
import DiagnosisCard from "../components/DiagnosisCard";
import Highlight from "../components/Highlight";

interface Msg {
  role: "user" | "assistant";
  content: string;
  citations?: any[];
  card?: any;
  ticket_id?: string | null;
  need_human?: boolean;
  from_cache?: boolean;
  message_id?: string;
  streaming?: boolean;
}

export default function Chat() {
  const [msgs, setMsgs] = useState<Msg[]>([]);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const convId = useRef<string | null>(null);

  const send = async () => {
    const text = input.trim();
    if (!text || sending) return;
    setInput("");
    setSending(true);
    // 先插入用户消息和一条占位的流式助手消息，后续 SSE 回调持续更新最后这条
    setMsgs((m) => [...m, { role: "user", content: text }, { role: "assistant", content: "", streaming: true }]);
    try {
      await chatStream(text, convId.current, {
        // meta：拿到会话/消息 id（首轮会创建新会话）
        onMeta: (m) => {
          convId.current = m.conversation_id;
          setMsgs((prev) => {
            const c = prev.slice();
            c[c.length - 1] = { ...c[c.length - 1], message_id: m.message_id };
            return c;
          });
        },
        // token：逐段追加到正文，形成打字机效果
        onToken: (t) =>
          setMsgs((prev) => {
            const c = prev.slice();
            const last = c[c.length - 1];
            c[c.length - 1] = { ...last, content: last.content + t };
            return c;
          }),
        // done：用完整结构化结果（卡片/引用/工单等）覆盖占位消息
        onDone: (d) =>
          setMsgs((prev) => {
            const c = prev.slice();
            c[c.length - 1] = {
              ...c[c.length - 1],
              streaming: false,
              content: d.answer ?? c[c.length - 1].content,
              card: d.card,
              citations: d.citations,
              ticket_id: d.ticket_id,
              need_human: d.need_human,
              from_cache: d.from_cache,
            };
            return c;
          }),
      });
    } catch {
      antMsg.error("对话失败");
      setMsgs((prev) => prev.filter((_, i) => i !== prev.length - 1));
    } finally {
      setSending(false);
    }
  };

  const feedback = async (type: string) => {
    if (!convId.current) {
      antMsg.info("请先开始对话");
      return;
    }
    const r = await submitFeedback({ conversation_id: convId.current, type });
    if (type === "need_human" && r.ticket_id) {
      antMsg.success(`已转人工，工单 ${r.ticket_id}`);
      setMsgs((m) => [
        ...m,
        { role: "assistant", content: `已为你转接人工技术支持，工单号 ${r.ticket_id}，技术支持会尽快跟进。`, ticket_id: r.ticket_id },
      ]);
    } else {
      antMsg.success(type === "resolved" ? "已标记为已解决" : "已记录");
    }
  };

  return (
    <div style={{ maxWidth: 860, margin: "0 auto" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8 }}>
        <Typography.Text strong>智能技术支持</Typography.Text>
        <Button size="small" onClick={() => feedback("need_human")}>🙋 转人工</Button>
      </div>
      <div style={{ minHeight: "60vh", marginBottom: 16 }}>
        {msgs.length === 0 && (
          <Typography.Paragraph type="secondary">
            试试：「实名认证接口返回401，request_id是 req_20260615_8842」「签名算法怎么生成」「这个月费用为什么变高」
          </Typography.Paragraph>
        )}
        {msgs.map((m, i) => {
          const isUser = m.role === "user";
          return (
          <div
            key={i}
            style={{ display: "flex", flexDirection: isUser ? "row-reverse" : "row", gap: 10, margin: "14px 0", alignItems: "flex-start" }}
          >
            <Avatar style={{ background: isUser ? "#1677ff" : "#52c41a", flexShrink: 0 }}>
              {isUser ? "🧑" : "🤖"}
            </Avatar>
            <Card size="small" style={{ maxWidth: "78%", background: isUser ? "#e6f4ff" : "#fff" }}>
              {isUser ? (
                <span style={{ whiteSpace: "pre-wrap" }}><Highlight text={m.content} /></span>
              ) : m.card ? (
                <DiagnosisCard card={m.card} />
              ) : m.content ? (
                <div className="md">
                  <ReactMarkdown remarkPlugins={[remarkGfm]}>{m.content}</ReactMarkdown>
                </div>
              ) : (
                m.streaming ? "思考中…" : ""
              )}
              {m.role === "assistant" && !m.streaming && (
                <div style={{ marginTop: 8 }}>
                  <Tag color="green">🤖 AI 助手</Tag>
                  {m.from_cache && <Tag color="gold">缓存命中</Tag>}
                  {m.need_human && <Tag color="volcano">已转人工</Tag>}
                  {m.ticket_id && <Tag color="blue">工单 {m.ticket_id}</Tag>}
                  {m.citations && m.citations.length > 0 && (
                    <div style={{ marginTop: 6 }}>
                      <Typography.Text type="secondary" style={{ fontSize: 12 }}>引用来源：</Typography.Text>
                      {m.citations.map((c: any, j: number) => (
                        <Tag key={j}>[{c.index}] 《{c.doc_title}》-{c.section}</Tag>
                      ))}
                    </div>
                  )}
                  <Space style={{ marginTop: 8 }}>
                    <Button size="small" onClick={() => feedback("resolved")}>✅ 已解决</Button>
                    <Button size="small" onClick={() => feedback("unresolved")}>❌ 没解决</Button>
                    <Button size="small" onClick={() => feedback("need_human")}>🙋 需要人工</Button>
                  </Space>
                </div>
              )}
            </Card>
          </div>
          );
        })}
      </div>
      <Space.Compact style={{ width: "100%" }}>
        <Input.TextArea
          value={input}
          onChange={(e) => setInput(e.target.value)}
          autoSize={{ minRows: 1, maxRows: 4 }}
          onPressEnter={(e) => { e.preventDefault(); send(); }}
          placeholder="描述你的问题…"
        />
        <Button type="primary" onClick={send} loading={sending}>发送</Button>
      </Space.Compact>
    </div>
  );
}
