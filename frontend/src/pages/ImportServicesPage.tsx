import { useMutation, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, FileSpreadsheet, Upload } from "lucide-react";
import { useState } from "react";
import { Link, useParams } from "react-router";

import { ApiError } from "../api/client";
import {
  confirmServiceImport,
  previewServiceImport,
  uploadServiceImport,
  type ImportMapping,
  type ImportPreview,
  type ImportResult,
  type ImportUpload,
} from "../api/imports";
import { useAuth } from "../auth/AuthProvider";
import { CustomSelect } from "../components/CustomSelect";
import { AICategorizationReview } from "../features/categorization/AICategorizationReview";

export function ImportServicesPage({
  embedded = false,
  onClose,
}: {
  embedded?: boolean;
  onClose?: () => void;
} = {}) {
  const { platformId = "" } = useParams();
  const auth = useAuth();
  const queryClient = useQueryClient();
  const [file, setFile] = useState<File | null>(null);
  const [uploaded, setUploaded] = useState<ImportUpload | null>(null);
  const [preview, setPreview] = useState<ImportPreview | null>(null);
  const [result, setResult] = useState<ImportResult | null>(null);
  const [ignoredRows, setIgnoredRows] = useState<Set<number>>(new Set());
  const [mapping, setMapping] = useState<ImportMapping>({
    name_column: 0,
    version_column: null,
    category_column: null,
    category_mode: "from_file",
  });
  const [duplicateStrategy, setDuplicateStrategy] = useState<
    "ignore" | "merge"
  >("ignore");
  const [categoryOverrides, setCategoryOverrides] = useState<
    Record<number, string>
  >({});
  const upload = useMutation({
    mutationFn: () => uploadServiceImport(platformId, file!),
    onSuccess: (data) => {
      setUploaded(data);
      setMapping((current) => ({
        ...current,
        name_column: data.columns[0]?.index ?? 0,
      }));
    },
  });
  const mappingPreview = useMutation({
    mutationFn: () => previewServiceImport(uploaded!.id, mapping),
    onSuccess: (data) => {
      setPreview(data);
      setIgnoredRows(
        new Set(
          data.rows
            .filter((row) => row.status === "invalid")
            .map((row) => row.row_number),
        ),
      );
    },
  });
  const confirmation = useMutation({
    mutationFn: () =>
      confirmServiceImport(
        uploaded!.id,
        [...ignoredRows],
        duplicateStrategy,
        categoryOverrides,
      ),
    onSuccess: async (data) => {
      setResult(data);
      await queryClient.invalidateQueries({
        queryKey: ["services", platformId],
      });
      await queryClient.invalidateQueries({
        queryKey: ["categories", platformId, "used"],
      });
      await queryClient.invalidateQueries({
        queryKey: ["platform-history", platformId],
      });
    },
  });
  const error =
    upload.error ??
    mappingPreview.error ??
    confirmation.error;

  if (!auth.hasPermission("service.import")) {
    return (
      <div className="form-error" role="alert">
        Vous n’avez pas l’autorisation d’importer des services.
      </div>
    );
  }

  if (result) {
    return (
      <section aria-labelledby="import-result-title" className="import-wizard">
        <p className="eyebrow">Import terminé</p>
        <h1 id="import-result-title">Résumé de l’import</h1>
        <dl className="detail-list">
          <div>
            <dt>Services créés</dt>
            <dd>{result.created}</dd>
          </div>
          <div>
            <dt>Services fusionnés</dt>
            <dd>{result.merged}</dd>
          </div>
          <div>
            <dt>Lignes ignorées</dt>
            <dd>{result.skipped}</dd>
          </div>
          <div>
            <dt>Catégories créées</dt>
            <dd>{result.categories_created}</dd>
          </div>
        </dl>
        {onClose ? (
          <button className="primary-button" type="button" onClick={onClose}>
            Terminer
          </button>
        ) : (
          <Link className="primary-button" to={`/platforms/${platformId}`}>
            Retour à la plateforme
          </Link>
        )}
      </section>
    );
  }

  return (
    <section
      aria-labelledby={embedded ? undefined : "import-title"}
      aria-label={embedded ? "Assistant d’import Excel" : undefined}
      className="import-wizard"
    >
      {!embedded && (
        <Link className="back-link" to={`/platforms/${platformId}`}>
          <ArrowLeft aria-hidden="true" />
          Retour à la plateforme
        </Link>
      )}
      {!embedded && (
        <>
          <p className="eyebrow">Ajout de services</p>
          <h1 id="import-title">Importer un fichier Excel</h1>
        </>
      )}
      <ol className="wizard-steps" aria-label="Progression">
        <li aria-current={!uploaded ? "step" : undefined}>1. Fichier</li>
        <li aria-current={uploaded && !preview ? "step" : undefined}>
          2. Mapping
        </li>
        <li aria-current={preview ? "step" : undefined}>3. Vérification</li>
      </ol>
      {error && (
        <div className="form-error" role="alert">
          {error instanceof ApiError ? error.message : "L’import a échoué."}
        </div>
      )}

      {!uploaded && (
        <form
          className="upload-panel"
          onSubmit={(event) => {
            event.preventDefault();
            if (file) upload.mutate();
          }}
        >
          <FileSpreadsheet aria-hidden="true" />
          <label htmlFor="excel-file">
            Fichier Excel (.xlsx, 5 Mio maximum)
          </label>
          <input
            id="excel-file"
            type="file"
            accept=".xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            onChange={(event) => setFile(event.target.files?.[0] ?? null)}
          />
          <button
            className="primary-button"
            type="submit"
            disabled={!file || upload.isPending}
          >
            <Upload aria-hidden="true" />{" "}
            {upload.isPending ? "Lecture…" : "Charger et analyser"}
          </button>
        </form>
      )}

      {uploaded && !preview && (
        <form
          className="mapping-form"
          onSubmit={(event) => {
            event.preventDefault();
            mappingPreview.mutate();
          }}
        >
          <p>
            <strong>{uploaded.filename}</strong> — {uploaded.row_count} ligne(s)
            détectée(s).
          </p>
          <MappingSelect
            label="Nom du service"
            required
            value={mapping.name_column}
            columns={uploaded.columns}
            onChange={(value) =>
              setMapping({ ...mapping, name_column: value! })
            }
          />
          <MappingSelect
            label="Version"
            value={mapping.version_column}
            columns={uploaded.columns}
            onChange={(value) =>
              setMapping({ ...mapping, version_column: value })
            }
          />
          <MappingSelect
            label="Catégorie"
            value={mapping.category_column}
            columns={uploaded.columns}
            onChange={(value) =>
              setMapping({
                ...mapping,
                category_column: value,
                category_mode: value === null ? "uncategorized" : "from_file",
              })
            }
          />
          <div className="table-wrapper">
            <table className="service-table">
              <thead>
                <tr>
                  {uploaded.columns.map((column) => (
                    <th key={column.index}>{column.name}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {uploaded.sample_rows.map((row, index) => (
                  <tr key={index}>
                    {uploaded.columns.map((column) => (
                      <td key={column.index}>{row[column.index]}</td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <button
            className="primary-button"
            type="submit"
            disabled={mappingPreview.isPending}
          >
            Valider le mapping
          </button>
        </form>
      )}

      {preview && (
        <div className="preview-panel">
          <div className="import-counts">
            <span>{preview.valid_count} valide(s)</span>
            <span>{preview.invalid_count} invalide(s)</span>
            <span>{preview.duplicate_count} doublon(s)</span>
          </div>
          <label htmlFor="duplicate-strategy">Services déjà existants</label>
          <CustomSelect
            id="duplicate-strategy"
            value={duplicateStrategy}
            onChange={(next) => setDuplicateStrategy(next as "ignore" | "merge")}
            options={[
              { value: "ignore", label: "Ignorer sans modifier" },
              { value: "merge", label: "Fusionner la catégorie et tracer l’import" },
            ]}
          />
          <AICategorizationReview
            platformId={platformId}
            items={preview.rows
              .filter((row) => row.status !== "invalid")
              .map((row) => ({
                key: String(row.row_number),
                name: row.name,
                version: row.version,
              }))}
            onConfirmed={async (suggestions) => {
              setCategoryOverrides((current) => ({
                ...current,
                ...Object.fromEntries(
                  suggestions.map((item) => [Number(item.key), item.category.name]),
                ),
              }));
              await queryClient.invalidateQueries({ queryKey: ["categories"] });
            }}
          />
          <div className="table-wrapper">
            <table className="service-table">
              <thead>
                <tr>
                  <th>Importer</th>
                  <th>Ligne</th>
                  <th>Service</th>
                  <th>Version</th>
                  <th>Catégorie</th>
                  <th>État</th>
                </tr>
              </thead>
              <tbody>
                {preview.rows.map((row) => (
                  <tr
                    key={row.row_number}
                    className={`import-row--${row.status}`}
                  >
                    <td>
                      <input
                        type="checkbox"
                        aria-label={`Importer la ligne ${row.row_number}`}
                        disabled={row.status === "invalid"}
                        checked={!ignoredRows.has(row.row_number)}
                        onChange={() =>
                          setIgnoredRows((current) => {
                            const next = new Set(current);
                            next.has(row.row_number)
                              ? next.delete(row.row_number)
                              : next.add(row.row_number);
                            return next;
                          })
                        }
                      />
                    </td>
                    <td>{row.row_number}</td>
                    <td>{row.name || "—"}</td>
                    <td>{row.version ?? "—"}</td>
                    <td>
                      <input
                        aria-label={`Catégorie de la ligne ${row.row_number}`}
                        value={
                          categoryOverrides[row.row_number] ??
                          row.category ??
                          ""
                        }
                        placeholder="Non catégorisé"
                        onChange={(event) =>
                          setCategoryOverrides({
                            ...categoryOverrides,
                            [row.row_number]: event.target.value,
                          })
                        }
                      />
                    </td>
                    <td>
                      {row.status === "valid" ? "Valide" : row.errors.join(" ")}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="form-actions">
            <button type="button" onClick={() => setPreview(null)}>
              Modifier le mapping
            </button>
            <button
              className="primary-button"
              type="button"
              onClick={() => confirmation.mutate()}
              disabled={confirmation.isPending}
            >
              {confirmation.isPending ? "Import…" : "Confirmer l’import"}
            </button>
          </div>
        </div>
      )}
    </section>
  );
}

function MappingSelect({
  label,
  required = false,
  value,
  columns,
  onChange,
}: {
  label: string;
  required?: boolean;
  value: number | null;
  columns: ImportUpload["columns"];
  onChange: (value: number | null) => void;
}) {
  const id = `mapping-${label.toLowerCase().replaceAll(" ", "-")}`;
  return (
    <div className="form-field">
      <label htmlFor={id}>
        {label}
        {required ? " (obligatoire)" : " (optionnel)"}
      </label>
      <CustomSelect
        id={id}
        value={value === null ? "" : String(value)}
        onChange={(next) => onChange(next === "" ? null : Number(next))}
        options={[
          ...(!required ? [{ value: "", label: "Ne pas importer" }] : []),
          ...columns.map((column) => ({ value: String(column.index), label: column.name })),
        ]}
      />
    </div>
  );
}
