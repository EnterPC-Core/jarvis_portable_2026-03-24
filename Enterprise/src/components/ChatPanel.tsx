import { Composer } from "./Composer";
import { MessageList } from "./MessageList";
import type { EnterpriseThread } from "../types";

type ChatPanelProps = {
  busy: boolean;
  composerText: string;
  thread: EnterpriseThread | null;
  onCancel: () => void;
  onComposerChange: (value: string) => void;
  onSend: () => void;
};

export function ChatPanel({
  busy,
  composerText,
  thread,
  onCancel,
  onComposerChange,
  onSend,
}: ChatPanelProps) {
  return (
    <section className="chat-shell">
      <div className="chat-shell-header">
        <div>
          <p className="eyebrow">Chat workspace</p>
          <h2>{thread?.localTitle ?? "Сессия не выбрана"}</h2>
        </div>
        <div className={`health-pill compact ${busy ? "working" : "healthy"}`}>
          {busy ? "Streaming via polling" : "Idle"}
        </div>
      </div>

      <MessageList messages={thread?.messages ?? []} />

      <Composer
        busy={busy}
        capabilitiesNote="Attachments, widgets и dictation честно отключены: серверный контракт для них пока не подтверждён."
        value={composerText}
        onCancel={onCancel}
        onChange={onComposerChange}
        onSend={onSend}
      />
    </section>
  );
}
