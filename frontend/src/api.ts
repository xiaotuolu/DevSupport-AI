/**
 * @repo: https://github.com/xiaotuolu/DevSupport-AI
 */
import axios from "axios";

const api = axios.create({ baseURL: "/api" });

// 每个请求自动带上本地存储的 JWT
api.interceptors.request.use((cfg) => {
  const token = localStorage.getItem("token");
  if (token) cfg.headers.Authorization = `Bearer ${token}`;
  return cfg;
});

export interface UserInfo {
  user_id: string;
  username: string;
  display_name: string;
  role: string;
  tenant_id: string;
  tenant_name?: string;
}

export const isInternal = (role: string) => role === "support" || role === "admin";

export async function login(username: string, password: string) {
  const { data } = await api.post("/auth/login", { username, password });
  localStorage.setItem("token", data.access_token);
  localStorage.setItem("user", JSON.stringify(data.user));
  return data.user as UserInfo;
}

export function logout() {
  localStorage.removeItem("token");
  localStorage.removeItem("user");
}

export function currentUser(): UserInfo | null {
  const raw = localStorage.getItem("user");
  return raw ? JSON.parse(raw) : null;
}

export const listConversations = () => api.get("/conversations").then((r) => r.data);
export const getConversation = (id: string) => api.get(`/conversations/${id}`).then((r) => r.data);
export const sendCustomerMessage = (id: string, content: string) => api.post(`/conversations/${id}/messages`, { content }).then((r) => r.data);
export const myTickets = () => api.get("/tickets").then((r) => r.data);
export const submitFeedback = (body: any) => api.post("/feedback", body).then((r) => r.data);
export const wbTickets = (params: any) => api.get("/workbench/tickets", { params }).then((r) => r.data);
export const wbTicketDetail = (id: string) => api.get(`/workbench/tickets/${id}`).then((r) => r.data);
export const wbUpdateTicket = (id: string, body: any) => api.post(`/workbench/tickets/${id}`, body).then((r) => r.data);
export const wbSuggestReply = (convId: string) => api.get(`/workbench/conversations/${convId}/suggest_reply`).then((r) => r.data);
export const wbReply = (convId: string, content: string) => api.post(`/workbench/conversations/${convId}/reply`, { content }).then((r) => r.data);
export const listDocs = () => api.get("/docs").then((r) => r.data);
export const getDoc = (id: string) => api.get(`/docs/${id}`).then((r) => r.data);
export const getTrace = (id: string) => api.get(`/traces/${id}`).then((r) => r.data);
export const getMetrics = () => api.get("/metrics").then((r) => r.data);

/** SSE over fetch（后端 /api/chat 为 POST + EventSource 不支持 POST，故手动解析）。*/
export async function chatStream(
  message: string,
  conversationId: string | null,
  handlers: {
    onMeta?: (m: any) => void;
    onToken?: (t: string) => void;
    onDone?: (d: any) => void;
  }
) {
  const resp = await fetch("/api/chat", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${localStorage.getItem("token")}`,
    },
    body: JSON.stringify({ message, conversation_id: conversationId }),
  });
  const reader = resp.body!.getReader();
  const decoder = new TextDecoder();
  let buf = "";
  let event = "";
  // 手动按 SSE 协议解析字节流：逐行拆 event:/data:，保留最后不完整行待下一块拼接
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buf += decoder.decode(value, { stream: true });
    const lines = buf.split("\n");
    buf = lines.pop() || "";
    for (const line of lines) {
      if (line.startsWith("event:")) event = line.slice(6).trim();
      else if (line.startsWith("data:")) {
        const data = line.slice(5).replace(/^ /, "");
        if (event === "meta") handlers.onMeta?.(JSON.parse(data));
        else if (event === "token") handlers.onToken?.(data);
        else if (event === "done") handlers.onDone?.(JSON.parse(data));
      }
    }
  }
}

export default api;
