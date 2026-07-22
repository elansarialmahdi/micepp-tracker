import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Check,
  Copy,
  Eye,
  EyeOff,
  KeyRound,
  MoreHorizontal,
  Pencil,
  Plus,
  ShieldCheck,
  Trash2,
  UserRound,
  X,
} from "lucide-react";
import { FormEvent, useRef, useState } from "react";

import { ApiError } from "../api/client";
import {
  archiveManagedUser,
  createManagedUser,
  getManagedUsers,
  getRoles,
  updateManagedUser,
  updateManagedUserPassword,
  type ManagedRole,
  type ManagedUser,
} from "../api/users";
import { useAuth } from "../auth/AuthProvider";
import { CustomSelect } from "../components/CustomSelect";
import { ModalPortal } from "../components/ModalPortal";
import { ViewportMenuPortal } from "../components/ViewportMenuPortal";

function mutationMessage(error: unknown, fallback: string): string {
  return error instanceof ApiError ? error.message : fallback;
}

function RoleSelect({
  roles,
  value,
  onChange,
  id,
}: {
  roles: ManagedRole[];
  value: string;
  onChange: (id: string) => void;
  id: string;
}) {
  const selectedRole = roles.find((role) => role.id === value);
  return (
    <div className="role-select-field">
      <CustomSelect
        id={id}
        value={value}
        onChange={onChange}
        ariaLabel="Rôle de l’utilisateur"
        placeholder="Choisir un rôle"
        options={roles.map((role) => ({ value: role.id, label: role.name }))}
      />
      {selectedRole?.description && (
        <small className="role-select-description">{selectedRole.description}</small>
      )}
    </div>
  );
}

async function copyToClipboard(value: string) {
  if (navigator.clipboard?.writeText) {
    await navigator.clipboard.writeText(value);
    return;
  }
  const input = document.createElement("textarea");
  input.value = value;
  input.style.position = "fixed";
  input.style.opacity = "0";
  document.body.appendChild(input);
  input.select();
  const copied = document.execCommand("copy");
  input.remove();
  if (!copied) throw new Error("Clipboard unavailable");
}

function PasswordField({
  id,
  value,
  onChange,
}: {
  id: string;
  value: string;
  onChange: (value: string) => void;
}) {
  const [visible, setVisible] = useState(false);
  const [copyState, setCopyState] = useState<"idle" | "copied" | "error">("idle");

  async function copyPassword() {
    if (!value) return;
    try {
      await copyToClipboard(value);
      setCopyState("copied");
    } catch {
      setCopyState("error");
    }
  }

  return (
    <>
      <div className="password-input-control">
        <input
          id={id}
          type={visible ? "text" : "password"}
          minLength={12}
          value={value}
          onChange={(event) => {
            onChange(event.target.value);
            setCopyState("idle");
          }}
          autoComplete="new-password"
          required
        />
        <div className="password-input-control__actions">
          <button
            type="button"
            onClick={() => setVisible((current) => !current)}
            aria-label={visible ? "Masquer le mot de passe" : "Afficher le mot de passe"}
            data-tooltip={visible ? "Masquer" : "Afficher"}
          >
            {visible ? <EyeOff aria-hidden="true" /> : <Eye aria-hidden="true" />}
          </button>
          <button
            type="button"
            onClick={() => void copyPassword()}
            disabled={!value}
            aria-label="Copier le mot de passe"
            data-tooltip="Copier"
          >
            {copyState === "copied" ? <Check aria-hidden="true" /> : <Copy aria-hidden="true" />}
          </button>
        </div>
      </div>
      <small>12 caractères minimum, avec majuscule, minuscule, chiffre et caractère spécial.</small>
      <span className={`password-copy-status password-copy-status--${copyState}`} aria-live="polite">
        {copyState === "copied"
          ? "Mot de passe copié."
          : copyState === "error"
            ? "Impossible de copier le mot de passe."
            : ""}
      </span>
    </>
  );
}

function ModalHeader({ id, eyebrow, title, onClose }: { id: string; eyebrow: string; title: string; onClose: () => void }) {
  return (
    <div className="section-header">
      <div><p className="eyebrow">{eyebrow}</p><h2 id={id}>{title}</h2></div>
      <button type="button" onClick={onClose} aria-label="Fermer"><X aria-hidden="true" /></button>
    </div>
  );
}

function CreateUserModal({ roles, onClose }: { roles: ManagedRole[]; onClose: () => void }) {
  const queryClient = useQueryClient();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [roleId, setRoleId] = useState("");
  const creation = useMutation({ mutationFn: createManagedUser });

  async function submit(event: FormEvent) {
    event.preventDefault();
    try {
      await creation.mutateAsync({ username: username.trim(), password, role_ids: [roleId] });
      await queryClient.invalidateQueries({ queryKey: ["managed-users"] });
      onClose();
    } catch {
      // The mutation error is rendered in the form.
    }
  }

  return (
    <ModalPortal><div className="modal-backdrop form-modal-backdrop" role="presentation" onMouseDown={(event) => event.target === event.currentTarget && onClose()}>
      <section className="settings-modal form-dialog user-create-modal" role="dialog" aria-modal="true" aria-labelledby="user-create-title">
        <ModalHeader id="user-create-title" eyebrow="Compte" title="Nouvel utilisateur" onClose={onClose} />
        <form className="platform-form" onSubmit={(event) => void submit(event)}>
          <div className="form-field"><label htmlFor="new-username">Identifiant</label><input id="new-username" value={username} onChange={(event) => setUsername(event.target.value)} autoComplete="off" required /></div>
          <div className="form-field"><label htmlFor="new-user-password">Mot de passe temporaire</label><PasswordField id="new-user-password" value={password} onChange={setPassword} /><small>L’utilisateur devra le modifier à sa première connexion.</small></div>
          <div className="form-field"><label htmlFor="new-user-role">Rôle</label><RoleSelect id="new-user-role" roles={roles} value={roleId} onChange={setRoleId} /></div>
          {creation.error && <div className="form-error" role="alert">{mutationMessage(creation.error, "La création a échoué.")}</div>}
          <div className="form-actions"><button type="button" onClick={onClose}>Annuler</button><button className="primary-button" type="submit" disabled={creation.isPending || !roleId}>Créer l’utilisateur</button></div>
        </form>
      </section>
    </div></ModalPortal>
  );
}

function EditUserModal({ user, roles, onClose }: { user: ManagedUser; roles: ManagedRole[]; onClose: () => void }) {
  const queryClient = useQueryClient();
  const [username, setUsername] = useState(user.username);
  const [roleId, setRoleId] = useState(user.roles[0]?.id ?? "");
  const update = useMutation({ mutationFn: () => updateManagedUser(user.id, { username: username.trim(), role_ids: [roleId] }) });

  async function submit(event: FormEvent) {
    event.preventDefault();
    try {
      await update.mutateAsync();
      await queryClient.invalidateQueries({ queryKey: ["managed-users"] });
      onClose();
    } catch {
      // The mutation error is rendered in the form.
    }
  }

  return (
    <ModalPortal><div className="modal-backdrop form-modal-backdrop" role="presentation" onMouseDown={(event) => event.target === event.currentTarget && onClose()}>
      <section className="settings-modal form-dialog user-edit-modal" role="dialog" aria-modal="true" aria-labelledby="user-edit-title">
        <ModalHeader id="user-edit-title" eyebrow="Utilisateur" title={`Modifier ${user.username}`} onClose={onClose} />
        <form className="platform-form" onSubmit={(event) => void submit(event)}>
          <div className="form-field"><label htmlFor={`edit-username-${user.id}`}>Identifiant</label><input id={`edit-username-${user.id}`} value={username} onChange={(event) => setUsername(event.target.value)} autoComplete="off" required /></div>
          <div className="form-field"><label htmlFor={`edit-role-${user.id}`}>Rôle</label><RoleSelect id={`edit-role-${user.id}`} roles={roles} value={roleId} onChange={setRoleId} /></div>
          {update.error && <div className="form-error" role="alert">{mutationMessage(update.error, "La modification a échoué.")}</div>}
          <div className="form-actions"><button type="button" onClick={onClose}>Annuler</button><button className="primary-button" type="submit" disabled={update.isPending || !username.trim() || !roleId}>Enregistrer</button></div>
        </form>
      </section>
    </div></ModalPortal>
  );
}

function PasswordModal({ user, onClose }: { user: ManagedUser; onClose: () => void }) {
  const [password, setPassword] = useState("");
  const [completed, setCompleted] = useState(false);
  const update = useMutation({ mutationFn: () => updateManagedUserPassword(user.id, password) });

  async function submit(event: FormEvent) {
    event.preventDefault();
    try {
      await update.mutateAsync();
      setCompleted(true);
    } catch {
      // The mutation error is rendered in the form.
    }
  }

  return (
    <ModalPortal><div className="modal-backdrop form-modal-backdrop" role="presentation" onMouseDown={(event) => event.target === event.currentTarget && onClose()}>
      <section className="settings-modal form-dialog user-password-modal" role="dialog" aria-modal="true" aria-labelledby="user-password-title">
        <ModalHeader id="user-password-title" eyebrow="Sécurité" title={`Changer le mot de passe de ${user.username}`} onClose={onClose} />
        {completed ? <div className="platform-form"><div className="success-message" role="status">Le mot de passe a été modifié et les sessions existantes ont été révoquées. L’utilisateur devra choisir un nouveau mot de passe à sa prochaine connexion.</div><div className="form-actions"><button className="primary-button" type="button" onClick={onClose}>Fermer</button></div></div> :
          <form className="platform-form" onSubmit={(event) => void submit(event)}>
            <div className="form-field"><label htmlFor={`reset-password-${user.id}`}>Nouveau mot de passe temporaire</label><PasswordField id={`reset-password-${user.id}`} value={password} onChange={setPassword} /></div>
            {update.error && <div className="form-error" role="alert">{mutationMessage(update.error, "Le changement de mot de passe a échoué.")}</div>}
            <div className="form-actions"><button type="button" onClick={onClose}>Annuler</button><button className="primary-button" type="submit" disabled={update.isPending || password.length < 12}>Changer le mot de passe</button></div>
          </form>}
      </section>
    </div></ModalPortal>
  );
}

function UserCard({ user, roles }: { user: ManagedUser; roles: ManagedRole[] }) {
  const queryClient = useQueryClient();
  const menuRef = useRef<HTMLDivElement>(null);
  const [menuOpen, setMenuOpen] = useState(false);
  const [editing, setEditing] = useState(false);
  const [changingPassword, setChangingPassword] = useState(false);
  const archive = useMutation({ mutationFn: () => archiveManagedUser(user.id) });

  async function remove() {
    setMenuOpen(false);
    if (!window.confirm(`Supprimer le compte « ${user.username} » ? Il ne pourra plus se connecter, mais son historique sera conservé.`)) return;
    try {
      await archive.mutateAsync();
      await queryClient.invalidateQueries({ queryKey: ["managed-users"] });
    } catch {
      // The mutation error is rendered on the card.
    }
  }

  return (
    <article className="user-card">
      <div className="action-menu user-action-menu" ref={menuRef}>
        <button type="button" aria-label={`Actions pour ${user.username}`} aria-haspopup="menu" aria-expanded={menuOpen} onClick={() => setMenuOpen((current) => !current)}><MoreHorizontal aria-hidden="true" /></button>
        {menuOpen && <ViewportMenuPortal anchorRef={menuRef} className="action-menu__content user-action-menu__content" onRequestClose={() => setMenuOpen(false)}>
          <button type="button" role="menuitem" onClick={() => { setEditing(true); setMenuOpen(false); }}><Pencil aria-hidden="true" />Modifier</button>
          <button type="button" role="menuitem" onClick={() => { setChangingPassword(true); setMenuOpen(false); }}><KeyRound aria-hidden="true" />Changer le mot de passe</button>
          <button className="action-menu__danger" type="button" role="menuitem" onClick={() => void remove()}><Trash2 aria-hidden="true" />Supprimer</button>
        </ViewportMenuPortal>}
      </div>
      <div className="user-card__identity"><span><UserRound aria-hidden="true" /></span><div><h2>{user.username}</h2></div></div>
      <div className="user-card__status"><ShieldCheck aria-hidden="true" /><span>{user.roles.map((role) => role.name).join(", ")}</span></div>
      {archive.error && <div className="form-error user-card__error" role="alert">{mutationMessage(archive.error, "La suppression a échoué.")}</div>}
      {editing && <EditUserModal user={user} roles={roles} onClose={() => setEditing(false)} />}
      {changingPassword && <PasswordModal user={user} onClose={() => setChangingPassword(false)} />}
    </article>
  );
}

export function UsersPage() {
  const auth = useAuth();
  const [creating, setCreating] = useState(false);
  const users = useQuery({ queryKey: ["managed-users"], queryFn: ({ signal }) => getManagedUsers(signal) });
  const roles = useQuery({ queryKey: ["roles"], queryFn: ({ signal }) => getRoles(signal) });

  return (
    <section className="users-page" aria-labelledby="users-title">
      <div className="page-header"><div><p className="eyebrow">Administration</p><h1 id="users-title">Utilisateurs & permissions</h1><p className="users-page__intro">Attribuez un accès administrateur, audit ou traitement.</p></div>
        {auth.hasPermission("user.manage") && <button className="primary-button" type="button" onClick={() => setCreating(true)}><Plus aria-hidden="true" /> Nouvel utilisateur</button>}
      </div>
      {(users.isPending || roles.isPending) && <p role="status">Chargement des utilisateurs…</p>}
      {(users.isError || roles.isError) && <div className="form-error" role="alert">Impossible de charger les utilisateurs.</div>}
      <div className="user-list">{users.data?.map((user) => auth.hasPermission("user.manage") && roles.data ? <UserCard user={user} roles={roles.data} key={user.id} /> : <article className="user-card user-card--readonly" key={user.id}><div className="user-card__identity"><span><UserRound aria-hidden="true" /></span><div><h2>{user.username}</h2></div></div><div className="user-card__status"><ShieldCheck aria-hidden="true" /><span>{user.roles.map((role) => role.name).join(", ")}</span></div></article>)}</div>
      {creating && roles.data && <CreateUserModal roles={roles.data} onClose={() => setCreating(false)} />}
    </section>
  );
}
