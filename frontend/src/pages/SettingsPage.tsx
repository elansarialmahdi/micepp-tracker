import { RealtimeProtectionCard } from "../features/realtime/RealtimeProtectionCard";

export function SettingsPage() {
  return (
    <section aria-labelledby="settings-title">
      <div className="page-header">
        <div className="page-title-block">
          <h1 id="settings-title">Paramètres</h1>
          <p>Configurez la fréquence des vérifications automatiques.</p>
        </div>
      </div>
      <RealtimeProtectionCard />
    </section>
  );
}
