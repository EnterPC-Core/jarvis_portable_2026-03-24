import { useState } from "react";

import type { EnterpriseThread, RuntimeEndpointState, RuntimeSnapshot } from "../types";

type ThreadSidebarProps = {
  activeThreadId: string | null;
  loadingRuntime: boolean;
  runtimeEndpoint: RuntimeEndpointState;
  runtime: RuntimeSnapshot | null;
  runtimeError: string;
  threads: EnterpriseThread[];
  onCreateThread: () => void;
  onDeleteThread: (threadId: string) => void;
  onRefreshHealth: () => void;
  onRenameThread: (threadId: string, title: string) => void;
  onResetRuntimeBaseUrl: () => void;
  onRuntimeBaseUrlChange: (value: string) => void;
  onSaveRuntimeBaseUrl: () => void;
  onSelectThread: (threadId: string) => void;
};

export function ThreadSidebar({
  activeThreadId,
  loadingRuntime,
  runtimeEndpoint,
  runtime,
  runtimeError,
  threads,
  onCreateThread,
  onDeleteThread,
  onRefreshHealth,
  onRenameThread,
  onResetRuntimeBaseUrl,
  onRuntimeBaseUrlChange,
  onSaveRuntimeBaseUrl,
  onSelectThread,
}: ThreadSidebarProps) {
  const [editingThreadId, setEditingThreadId] = useState<string | null>(null);
  const [draftTitle, setDraftTitle] = useState("");

  return (
    <aside className="sidebar">
      <section className="sidebar-card">
        <div className="sidebar-card-header">
          <h2>Runtime</h2>
          <button className="secondary-button" onClick={onRefreshHealth} type="button">
            Обновить
          </button>
        </div>
        <label className="field-label" htmlFor="enterprise-core-url">
          Enterprise Core URL
        </label>
        <div className="runtime-url-row">
          <input
            className="thread-title-input"
            id="enterprise-core-url"
            placeholder="http://192.168.1.10:8766"
            value={runtimeEndpoint.draftBaseUrl}
            onChange={(event) => onRuntimeBaseUrlChange(event.target.value)}
          />
          <button className="secondary-button" onClick={onSaveRuntimeBaseUrl} type="button">
            Сохранить
          </button>
        </div>
        <div className="runtime-actions">
          <span className="muted">Активный адрес: {runtimeEndpoint.baseUrl}</span>
          <button className="ghost-button" onClick={onResetRuntimeBaseUrl} type="button">
            Сброс
          </button>
        </div>
        <p className="muted">
          Для APK укажи полный адрес Enterprise Core. <code>127.0.0.1</code> подходит только когда
          сервер реально доступен внутри самого приложения.
        </p>
        {loadingRuntime ? <p className="muted">Проверяю Enterprise Core...</p> : null}
        {runtimeEndpoint.error ? <p className="error-copy">{runtimeEndpoint.error}</p> : null}
        {runtimeError ? <p className="error-copy">{runtimeError}</p> : null}
        {runtime ? (
          <div className="runtime-grid">
            <span>Bridge</span>
            <strong>{runtime.bridge_alive ? "alive" : "down"}</strong>
            <span>Server</span>
            <strong>{runtime.enterprise_alive ? "alive" : "down"}</strong>
            <span>Supervisor</span>
            <strong>{runtime.supervisor_alive ? "alive" : "down"}</strong>
          </div>
        ) : null}
      </section>

      <section className="sidebar-card">
        <div className="sidebar-card-header">
          <h2>Сессии</h2>
          <button className="primary-button" onClick={onCreateThread} type="button">
            Новая
          </button>
        </div>
        <div className="thread-list">
          {threads.map((thread) => {
            const isActive = thread.id === activeThreadId;
            const messageCount = thread.messages.length;
            return (
              <article
                className={`thread-item ${isActive ? "active" : ""}`}
                key={thread.id}
                onClick={() => onSelectThread(thread.id)}
              >
                {editingThreadId === thread.id ? (
                  <form
                    className="thread-edit-form"
                    onSubmit={(event) => {
                      event.preventDefault();
                      onRenameThread(thread.id, draftTitle);
                      setEditingThreadId(null);
                      setDraftTitle("");
                    }}
                  >
                    <input
                      autoFocus
                      className="thread-title-input"
                      value={draftTitle}
                      onChange={(event) => setDraftTitle(event.target.value)}
                    />
                  </form>
                ) : (
                  <>
                    <div className="thread-item-main">
                      <strong>{thread.localTitle}</strong>
                      <span>{messageCount} сообщений</span>
                    </div>
                    <div className="thread-item-actions">
                      <button
                        className="ghost-button"
                        onClick={(event) => {
                          event.stopPropagation();
                          setEditingThreadId(thread.id);
                          setDraftTitle(thread.localTitle);
                        }}
                        type="button"
                      >
                        Имя
                      </button>
                      <button
                        className="ghost-button danger"
                        onClick={(event) => {
                          event.stopPropagation();
                          onDeleteThread(thread.id);
                        }}
                        type="button"
                      >
                        Удалить
                      </button>
                    </div>
                  </>
                )}
              </article>
            );
          })}
        </div>
      </section>

      <section className="sidebar-card">
        <h2>Подтверждённые ограничения</h2>
        <ul className="bullet-list">
          <li>Thread list сейчас локальный, потому что server-side thread API не подтверждён.</li>
          <li>Cancel останавливает локальный polling, но не серверную задачу.</li>
          <li>Attachments, widgets и dictation выключены до появления подтверждённых endpoint’ов.</li>
        </ul>
      </section>
    </aside>
  );
}
