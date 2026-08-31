/**
 * @repo: https://github.com/xiaotuolu/DevSupport-AI
 */
import { BrowserRouter, Routes, Route, Navigate, Link, useLocation, useNavigate } from "react-router-dom";
import { Layout, Menu, Button, Typography } from "antd";
import { currentUser, isInternal, logout } from "./api";
import Login from "./pages/Login";
import Chat from "./pages/Chat";
import Conversations from "./pages/Conversations";
import Docs from "./pages/Docs";
import MyTickets from "./pages/MyTickets";
import Workbench from "./pages/Workbench";
import Metrics from "./pages/Metrics";

const { Header, Content } = Layout;

// 路由守卫：未登录跳登录页；internal 路由对非内部角色拦回首页
function Guard({ children, internal }: { children: JSX.Element; internal?: boolean }) {
  const user = currentUser();
  if (!user) return <Navigate to="/login" replace />;
  if (internal && !isInternal(user.role)) return <Navigate to="/" replace />;
  return children;
}

function Shell({ children }: { children: JSX.Element }) {
  const user = currentUser();
  const loc = useLocation();
  const nav = useNavigate();
  if (!user) return children;
  const items = [
    { key: "/", label: <Link to="/">智能助手</Link> },
    { key: "/docs", label: <Link to="/docs">文档中心</Link> },
    { key: "/conversations", label: <Link to="/conversations">我的会话</Link> },
    { key: "/tickets", label: <Link to="/tickets">我的工单</Link> },
    // 工作台与运营指标仅内部角色可见
    ...(isInternal(user.role)
      ? [
          { key: "/workbench", label: <Link to="/workbench">工作台</Link> },
          { key: "/metrics", label: <Link to="/metrics">运营指标</Link> },
        ]
      : []),
  ];
  return (
    <Layout style={{ minHeight: "100vh" }}>
      <Header style={{ display: "flex", alignItems: "center", gap: 24 }}>
        <Typography.Title level={4} style={{ color: "#fff", margin: 0 }}>
          DevSupport AI
        </Typography.Title>
        <Menu theme="dark" mode="horizontal" selectedKeys={[loc.pathname]} items={items} style={{ flex: 1 }} />
        <span style={{ color: "#fff" }}>
          {user.display_name}（{user.role}）
        </span>
        <Button size="small" onClick={() => { logout(); nav("/login"); }}>
          退出
        </Button>
      </Header>
      <Content style={{ padding: 16, background: "#f5f5f5" }}>{children}</Content>
    </Layout>
  );
}

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route path="/" element={<Guard><Shell><Chat /></Shell></Guard>} />
        <Route path="/docs" element={<Guard><Shell><Docs /></Shell></Guard>} />
        <Route path="/conversations" element={<Guard><Shell><Conversations /></Shell></Guard>} />
        <Route path="/tickets" element={<Guard><Shell><MyTickets /></Shell></Guard>} />
        <Route path="/workbench" element={<Guard internal><Shell><Workbench /></Shell></Guard>} />
        <Route path="/metrics" element={<Guard internal><Shell><Metrics /></Shell></Guard>} />
      </Routes>
    </BrowserRouter>
  );
}
