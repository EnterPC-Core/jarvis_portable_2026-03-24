export type MessageRole = "user" | "assistant" | "system";

export type MessageStatus = "idle" | "streaming" | "done" | "error" | "cancelled";

export type EnterpriseMessage = {
  id: string;
  role: MessageRole;
  content: string;
  createdAt: string;
  status: MessageStatus;
  progressEvents: string[];
  error?: string;
  jobId?: string;
};

export type EnterpriseThread = {
  id: string;
  localTitle: string;
  serverChatId: number;
  createdAt: string;
  updatedAt: string;
  messages: EnterpriseMessage[];
};

export type RuntimeSnapshot = {
  ok: boolean;
  service?: string;
  ts?: number;
  supervisor_alive?: boolean;
  bridge_alive?: boolean;
  enterprise_alive?: boolean;
  supervisor_pid?: number;
  bridge_pid?: number;
  enterprise_pid?: number;
};

export type RuntimeEndpointState = {
  baseUrl: string;
  draftBaseUrl: string;
  error: string;
};

export type JobSnapshot = {
  ok?: boolean;
  id: string;
  done: boolean;
  answer: string;
  error: string;
  events: string[];
  updated_at?: number;
  exit_code?: number | null;
};

export type SendMessageResult = {
  jobId: string;
};

export type UnsupportedResult = {
  ok: false;
  reason: string;
};

export type EnterpriseCapabilities = {
  serverThreads: false;
  serverCancel: false;
  attachments: false;
  widgets: false;
  dictation: false;
};
