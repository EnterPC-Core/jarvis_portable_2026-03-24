type ComposerProps = {
  busy: boolean;
  capabilitiesNote: string;
  value: string;
  onCancel: () => void;
  onChange: (value: string) => void;
  onSend: () => void;
};

export function Composer({
  busy,
  capabilitiesNote,
  value,
  onCancel,
  onChange,
  onSend,
}: ComposerProps) {
  return (
    <footer className="composer">
      <label className="composer-label" htmlFor="enterprise-prompt">
        Запрос
      </label>
      <textarea
        id="enterprise-prompt"
        className="composer-input"
        placeholder="Опишите задачу для Enterprise Core"
        value={value}
        onChange={(event) => onChange(event.target.value)}
      />
      <div className="composer-footer">
        <p className="muted">{capabilitiesNote}</p>
        <div className="composer-actions">
          <button className="secondary-button" disabled={!busy} onClick={onCancel} type="button">
            Stop
          </button>
          <button className="primary-button" disabled={!value.trim() || busy} onClick={onSend} type="button">
            Send
          </button>
        </div>
      </div>
    </footer>
  );
}
