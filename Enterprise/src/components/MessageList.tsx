import type { EnterpriseMessage } from "../types";

type MessageListProps = {
  messages: EnterpriseMessage[];
};

export function MessageList({ messages }: MessageListProps) {
  if (messages.length === 0) {
    return (
      <section className="empty-state">
        <h2>Готово к работе</h2>
        <p>
          Отправьте запрос в Enterprise Core. Приложение создаст job через
          <code>/api/jobs</code>, будет опрашивать{" "}
          <code>/api/jobs/&lt;job_id&gt;</code> и покажет прогресс из{" "}
          <code>events</code> до финального <code>answer</code>.
        </p>
        <div className="starter-grid">
          <div>Проверь runtime</div>
          <div>Покажи статус bridge</div>
          <div>Собери короткий отчёт по проекту</div>
        </div>
      </section>
    );
  }

  return (
    <section className="message-list">
      {messages.map((message) => (
        <article className={`message-bubble ${message.role}`} key={message.id}>
          <header>
            <span>{message.role === "user" ? "Вы" : "Enterprise"}</span>
            <span className={`message-status ${message.status}`}>{message.status}</span>
          </header>
          <div className="message-content">
            {message.content ? <p>{message.content}</p> : <p className="muted">Ожидаю финальный answer...</p>}
            {message.error ? <p className="error-copy">{message.error}</p> : null}
          </div>
          {message.progressEvents.length > 0 ? (
            <div className="progress-card">
              <strong>События выполнения</strong>
              <ul>
                {message.progressEvents.slice(-6).map((entry) => (
                  <li key={`${message.id}:${entry}`}>{entry}</li>
                ))}
              </ul>
            </div>
          ) : null}
        </article>
      ))}
    </section>
  );
}
