/**
 * @repo: https://github.com/xiaotuolu/DevSupport-AI
 */
import { useState } from "react";
import { Card, Form, Input, Button, message, Typography, Tag, Space } from "antd";
import { useNavigate } from "react-router-dom";
import { login, isInternal } from "../api";

const DEMO = [
  ["dev_acme", "Acme 开发者（客户）"],
  ["admin_acme", "Acme 管理员（客户）"],
  ["support1", "技术支持（内部）"],
  ["admin", "系统管理员（内部）"],
];

export default function Login() {
  const nav = useNavigate();
  const [loading, setLoading] = useState(false);
  const [form] = Form.useForm();

  const onFinish = async (v: any) => {
    setLoading(true);
    try {
      const user = await login(v.username, v.password);
      message.success(`欢迎，${user.display_name}`);
      // 内部角色登录后进工作台，客户进智能助手首页
      nav(isInternal(user.role) ? "/workbench" : "/");
    } catch {
      message.error("用户名或密码错误");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{ display: "flex", justifyContent: "center", alignItems: "center", minHeight: "100vh", background: "#f0f2f5" }}>
      <Card style={{ width: 420 }}>
        <Typography.Title level={3} style={{ textAlign: "center" }}>
          DevSupport AI
        </Typography.Title>
        <Typography.Paragraph type="secondary" style={{ textAlign: "center" }}>
          面向 API 开放平台的多 Agent 智能技术支持
        </Typography.Paragraph>
        <Form form={form} onFinish={onFinish} layout="vertical">
          <Form.Item name="username" label="用户名" rules={[{ required: true }]}>
            <Input placeholder="dev_acme" />
          </Form.Item>
          <Form.Item name="password" label="密码" rules={[{ required: true }]}>
            <Input.Password placeholder="password123" />
          </Form.Item>
          <Button type="primary" htmlType="submit" loading={loading} block>
            登录
          </Button>
        </Form>
        <Typography.Paragraph type="secondary" style={{ marginTop: 16, fontSize: 12 }}>
          预置账号（密码均为 password123）：
          <Space wrap style={{ marginTop: 8 }}>
            {DEMO.map(([u, d]) => (
              <Tag key={u} style={{ cursor: "pointer" }} onClick={() => form.setFieldsValue({ username: u, password: "password123" })}>
                {u} · {d}
              </Tag>
            ))}
          </Space>
        </Typography.Paragraph>
      </Card>
    </div>
  );
}
