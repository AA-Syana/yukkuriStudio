export default function ErrorBanner({ message, onClose }: { message: string | null; onClose?: () => void }) {
  if (!message) return null;
  return (
    <div className="error-banner" role="alert">
      <span>{message}</span>
      {onClose && (
        <button className="link-button" onClick={onClose}>
          閉じる
        </button>
      )}
    </div>
  );
}
