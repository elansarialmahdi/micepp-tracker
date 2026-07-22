import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, ClipboardCheck, Server, ShieldAlert, X, XCircle } from "lucide-react";
import { FormEvent, useState } from "react";
import { Link } from "react-router";

import { ApiError } from "../api/client";
import {
  cancelTreatment,
  confirmTreatment,
  getMyTreatments,
  getTreatments,
  submitTreatment,
  type Treatment,
} from "../api/treatments";
import { ModalPortal } from "../components/ModalPortal";

const statusLabels: Record<Treatment["status"], string> = {
  assigned: "À traiter",
  submitted: "En attente de validation",
  confirmed: "Confirmé",
  cancelled: "Annulé",
};

function TreatmentCard({ treatment, admin, onSubmit, onConfirm, onCancel }: {
  treatment: Treatment;
  admin: boolean;
  onSubmit?: (item: Treatment) => void;
  onConfirm?: (item: Treatment) => void;
  onCancel?: (item: Treatment) => void;
}) {
  return (
    <article className={`treatment-card treatment-card--${treatment.status}`}>
      <div className="treatment-card__top">
        <span className="treatment-card__icon"><ShieldAlert aria-hidden="true" /></span>
        <div><span className="treatment-status">{statusLabels[treatment.status]}</span><h2>{treatment.service_name}</h2><p>Version vulnérable : {treatment.service_version_before ?? "Non renseignée"}</p></div>
        <time dateTime={treatment.assigned_at}>{new Date(treatment.assigned_at).toLocaleString("fr-FR")}</time>
      </div>
      <dl className="treatment-card__facts">
        <div><dt>Plateforme</dt><dd>{treatment.platform_name}</dd></div>
        <div><dt>Service</dt><dd>{admin ? <Link to={`/services/${treatment.service_id}`}>{treatment.service_name}</Link> : treatment.service_name}</dd></div>
        <div><dt>Version actuelle</dt><dd>{treatment.service_version ?? "Non renseignée"}</dd></div>
        <div><dt>Traitant</dt><dd>{treatment.assignee?.display_name ?? "Compte indisponible"}</dd></div>
      </dl>
      {treatment.assignment_note && <div className="treatment-note"><strong>Note de l’administrateur</strong><p>{treatment.assignment_note}</p></div>}
      {treatment.completion_note && <div className="treatment-note"><strong>Compte rendu du traitant</strong><p>{treatment.completion_note}</p></div>}
      {treatment.new_version && <p className="treatment-version">Version proposée : <strong>{treatment.new_version}</strong></p>}
      <div className="treatment-card__actions">
        {!admin && treatment.status === "assigned" && <button className="primary-button" type="button" onClick={() => onSubmit?.(treatment)}><ClipboardCheck aria-hidden="true" /> Déclarer comme traitée</button>}
        {admin && treatment.status === "submitted" && <button className="primary-button" type="button" onClick={() => onConfirm?.(treatment)}><CheckCircle2 aria-hidden="true" /> Confirmer le traitement</button>}
        {admin && ["assigned", "submitted"].includes(treatment.status) && <button className="treatment-cancel-button" type="button" onClick={() => onCancel?.(treatment)}><XCircle aria-hidden="true" /> Annuler le traitement</button>}
      </div>
    </article>
  );
}

function SubmitTreatmentModal({ treatment, onClose }: { treatment: Treatment; onClose: () => void }) {
  const queryClient = useQueryClient();
  const [version, setVersion] = useState("");
  const [note, setNote] = useState("");
  const mutation = useMutation({ mutationFn: () => submitTreatment(treatment.id, { new_version: version.trim(), note: note.trim() || null }) });
  async function submit(event: FormEvent) {
    event.preventDefault();
    await mutation.mutateAsync();
    await queryClient.invalidateQueries({ queryKey: ["my-treatments"] });
    onClose();
  }
  return (
    <ModalPortal><div className="modal-backdrop form-modal-backdrop" role="presentation" onMouseDown={(event) => event.target === event.currentTarget && onClose()}>
      <section className="settings-modal treatment-modal form-dialog" role="dialog" aria-modal="true" aria-labelledby="complete-treatment-title">
        <div className="section-header"><div><p className="eyebrow">{treatment.service_name} · {treatment.service_version_before ?? "Version non renseignée"}</p><h2 id="complete-treatment-title">Déclarer le traitement terminé</h2></div><button type="button" onClick={onClose} aria-label="Fermer"><X aria-hidden="true" /></button></div>
        <form className="platform-form" onSubmit={(event) => void submit(event)}>
          <p className="modal-help-text">Service {treatment.service_name} sur {treatment.platform_name}</p>
          <div className="form-field"><label htmlFor="treatment-new-version">Nouvelle version installée</label><input id="treatment-new-version" value={version} onChange={(event) => setVersion(event.target.value)} required /></div>
          <div className="form-field"><label htmlFor="treatment-completion-note">Compte rendu (optionnel)</label><textarea id="treatment-completion-note" rows={4} value={note} onChange={(event) => setNote(event.target.value)} /></div>
          {mutation.error && <div className="form-error" role="alert">{mutation.error instanceof ApiError ? mutation.error.message : "La déclaration a échoué."}</div>}
          <div className="form-actions"><button type="button" onClick={onClose}>Annuler</button><button className="primary-button" type="submit" disabled={mutation.isPending || !version.trim()}>Envoyer à l’administrateur</button></div>
        </form>
      </section>
    </div></ModalPortal>
  );
}

export function MyTreatmentsPage() {
  const [selected, setSelected] = useState<Treatment | null>(null);
  const treatments = useQuery({ queryKey: ["my-treatments"], queryFn: ({ signal }) => getMyTreatments(signal), refetchInterval: 5_000, refetchIntervalInBackground: true });
  return (
    <section className="treatments-page" aria-labelledby="my-treatments-title">
      <div className="page-header"><div><p className="eyebrow">Traitement</p><h1 id="my-treatments-title">Traitements à faire</h1><p className="treatments-intro">Les services et versions vulnérables qui vous ont été attribués.</p></div><span className="activity-live"><span aria-hidden="true" /> Actualisation toutes les 5 secondes</span></div>
      {treatments.isPending && <p role="status">Chargement des traitements…</p>}
      {treatments.isError && <div className="form-error">Impossible de charger les traitements.</div>}
      {treatments.data?.length === 0 && <div className="treatment-empty"><CheckCircle2 aria-hidden="true" /><h2>Aucun traitement en attente</h2></div>}
      <div className="treatment-list">{treatments.data?.map((item) => <TreatmentCard key={item.id} treatment={item} admin={false} onSubmit={setSelected} />)}</div>
      {selected && <SubmitTreatmentModal treatment={selected} onClose={() => setSelected(null)} />}
    </section>
  );
}

export function AdminTreatmentsPage() {
  const queryClient = useQueryClient();
  const [state, setState] = useState<"open" | "all" | "submitted" | "confirmed" | "cancelled">("open");
  const treatments = useQuery({ queryKey: ["treatments", state], queryFn: ({ signal }) => getTreatments(signal, state), refetchInterval: 5_000, refetchIntervalInBackground: true });
  const confirmation = useMutation({ mutationFn: confirmTreatment, onSuccess: async () => { await queryClient.invalidateQueries({ queryKey: ["treatments"] }); await queryClient.invalidateQueries({ queryKey: ["services"] }); } });
  const cancellation = useMutation({ mutationFn: cancelTreatment, onSuccess: async () => { await queryClient.invalidateQueries({ queryKey: ["treatments"] }); await queryClient.invalidateQueries({ queryKey: ["my-treatments"] }); } });
  function cancel(item: Treatment) {
    if (window.confirm(`Annuler le traitement de ${item.service_name} ${item.service_version_before ?? ""} attribué à ${item.assignee?.display_name ?? "cet utilisateur"} ?`)) cancellation.mutate(item.id);
  }
  return (
    <section className="treatments-page" aria-labelledby="treatments-title">
      <div className="page-header"><div><p className="eyebrow">Administration</p><h1 id="treatments-title">Demandes de traitement</h1><p className="treatments-intro">Suivez les attributions et confirmez les nouvelles versions.</p></div><span className="activity-live"><span aria-hidden="true" /> Actualisation toutes les 5 secondes</span></div>
      <div className="treatment-filters" role="group" aria-label="Filtrer les demandes">{([['open','En cours'],['submitted','À confirmer'],['confirmed','Confirmées'],['cancelled','Annulées'],['all','Toutes']] as const).map(([value,label]) => <button className={state === value ? "is-active" : ""} key={value} type="button" onClick={() => setState(value)}>{label}</button>)}</div>
      {confirmation.error && <div className="form-error" role="alert">{confirmation.error instanceof ApiError ? confirmation.error.message : "La confirmation a échoué."}</div>}
      {cancellation.error && <div className="form-error" role="alert">{cancellation.error instanceof ApiError ? cancellation.error.message : "L’annulation a échoué."}</div>}
      {treatments.isPending && <p role="status">Chargement des demandes…</p>}
      {treatments.data?.length === 0 && <div className="treatment-empty"><Server aria-hidden="true" /><h2>Aucune demande dans cette vue</h2></div>}
      <div className="treatment-list">{treatments.data?.map((item) => <TreatmentCard key={item.id} treatment={item} admin onConfirm={(target) => confirmation.mutate(target.id)} onCancel={cancel} />)}</div>
    </section>
  );
}
