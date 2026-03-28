type AppHeaderProps = {
  runtimeHealthy: boolean;
};

export function AppHeader({ runtimeHealthy }: AppHeaderProps) {
  return (
    <header className="app-header">
      <div>
        <p className="eyebrow">Enterprise Core Mobile</p>
        <h1>Enterprise</h1>
        <p className="header-copy">
          Android-оболочка вокруг Enterprise Core без OpenAI runtime backend.
          UI опирается на официальные ChatKit и Apps SDK примеры, а поток идёт
          через подтверждённый контракт `/api/jobs`.
        </p>
      </div>
      <div className={`health-pill ${runtimeHealthy ? "healthy" : "degraded"}`}>
        {runtimeHealthy ? "Enterprise Core online" : "Enterprise Core degraded"}
      </div>
    </header>
  );
}
