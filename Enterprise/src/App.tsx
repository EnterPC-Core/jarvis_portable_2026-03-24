import { AppHeader } from "./components/AppHeader";
import { ChatPanel } from "./components/ChatPanel";
import { ThreadSidebar } from "./components/ThreadSidebar";
import { useEnterpriseWorkspace } from "./hooks/useEnterpriseWorkspace";

export default function App() {
  const workspace = useEnterpriseWorkspace();

  return (
    <main className="app-shell">
      <div className="app-frame">
        <AppHeader runtimeHealthy={Boolean(workspace.runtime?.ok && workspace.runtime?.enterprise_alive)} />
        <div className="workspace-grid">
          <ThreadSidebar
            activeThreadId={workspace.activeThreadId}
            loadingRuntime={workspace.loadingRuntime}
            runtimeEndpoint={workspace.runtimeEndpoint}
            runtime={workspace.runtime}
            runtimeError={workspace.runtimeError}
            threads={workspace.threads}
            onCreateThread={workspace.createThread}
            onDeleteThread={workspace.deleteThread}
            onRefreshHealth={workspace.refreshHealth}
            onRenameThread={workspace.renameThread}
            onResetRuntimeBaseUrl={workspace.resetRuntimeBaseUrl}
            onRuntimeBaseUrlChange={(value) =>
              workspace.setRuntimeEndpoint((current) => ({
                ...current,
                draftBaseUrl: value,
                error: "",
              }))
            }
            onSaveRuntimeBaseUrl={workspace.saveRuntimeBaseUrl}
            onSelectThread={workspace.selectThread}
          />
          <ChatPanel
            busy={workspace.busyThreadId === workspace.activeThreadId}
            composerText={workspace.composerText}
            thread={workspace.activeThread}
            onCancel={workspace.cancelActiveResponse}
            onComposerChange={workspace.setComposerText}
            onSend={workspace.sendMessage}
          />
        </div>
      </div>
    </main>
  );
}
