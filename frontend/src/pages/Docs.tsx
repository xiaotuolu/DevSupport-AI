/**
 * @repo: https://github.com/xiaotuolu/DevSupport-AI
 */
import { useEffect, useState } from "react";
import { Card, Row, Col, Menu, Tag, Spin, Typography } from "antd";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { listDocs, getDoc } from "../api";

export default function Docs() {
  const [docs, setDocs] = useState<any[]>([]);
  const [current, setCurrent] = useState<any>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    listDocs().then((d) => {
      setDocs(d.documents);
      if (d.documents[0]) open(d.documents[0].id);  // 默认展开第一篇
    });
  }, []);

  const open = async (id: string) => {
    setLoading(true);
    try {
      setCurrent(await getDoc(id));
    } finally {
      setLoading(false);
    }
  };

  return (
    <Row gutter={12} style={{ maxWidth: 1200, margin: "0 auto" }}>
      <Col span={6}>
        <Card title="文档中心" size="small">
          <Menu
            mode="inline"
            selectedKeys={current ? [current.id] : []}
            onClick={(e) => open(e.key)}
            items={docs.map((d) => ({
              key: d.id,
              label: (
                <span>
                  {d.title} <Tag>{d.category}</Tag>
                </span>
              ),
            }))}
          />
        </Card>
      </Col>
      <Col span={18}>
        <Card size="small" style={{ minHeight: "70vh" }}>
          {loading ? (
            <Spin />
          ) : current ? (
            <>
              <Typography.Title level={4}>{current.title}</Typography.Title>
              <Tag color="blue">{current.category}</Tag>
              <div className="md" style={{ marginTop: 16 }}>
                <ReactMarkdown remarkPlugins={[remarkGfm]}>{current.content}</ReactMarkdown>
              </div>
            </>
          ) : (
            <Typography.Text type="secondary">选择左侧文档查看</Typography.Text>
          )}
        </Card>
      </Col>
    </Row>
  );
}
