/**
 * @repo: https://github.com/xiaotuolu/DevSupport-AI
 */
import { useEffect, useState } from "react";
import { Card, Table, Tag } from "antd";
import { myTickets } from "../api";

const PRIORITY_COLOR: Record<string, string> = { P0: "red", P1: "volcano", P2: "blue", P3: "default" };

export default function MyTickets() {
  const [data, setData] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  useEffect(() => {
    myTickets().then((d) => setData(d.tickets)).finally(() => setLoading(false));
  }, []);
  return (
    <Card title="我的工单" style={{ maxWidth: 1000, margin: "0 auto" }}>
      <Table
        rowKey="ticket_id"
        loading={loading}
        dataSource={data}
        columns={[
          { title: "工单号", dataIndex: "ticket_id" },
          { title: "标题", dataIndex: "title" },
          { title: "类型", dataIndex: "category" },
          { title: "优先级", dataIndex: "priority", render: (p) => <Tag color={PRIORITY_COLOR[p]}>{p}</Tag> },
          { title: "状态", dataIndex: "status", render: (s) => <Tag>{s}</Tag> },
          { title: "错误码", dataIndex: "error_code" },
          { title: "创建时间", dataIndex: "created_at", render: (t) => t?.replace("T", " ").slice(0, 19) },
        ]}
      />
    </Card>
  );
}
