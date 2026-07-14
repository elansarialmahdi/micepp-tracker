import { apiRequest } from "./client";

export type ImportColumn = { index: number; name: string };
export type ImportUpload = {
  id: string;
  filename: string;
  columns: ImportColumn[];
  sample_rows: string[][];
  row_count: number;
  ai_categorization_available: boolean;
};
export type ImportMapping = {
  name_column: number;
  version_column: number | null;
  category_column: number | null;
  category_mode: "from_file" | "uncategorized" | "ai";
};
export type ImportPreviewRow = {
  row_number: number;
  name: string;
  version: string | null;
  category: string | null;
  status: "valid" | "invalid" | "duplicate";
  duplicate_kind: "file" | "existing" | null;
  errors: string[];
};
export type ImportPreview = {
  id: string;
  rows: ImportPreviewRow[];
  valid_count: number;
  invalid_count: number;
  duplicate_count: number;
};
export type ImportResult = {
  created: number;
  merged: number;
  skipped: number;
  invalid: number;
  categories_created: number;
};

export function uploadServiceImport(platformId: string, file: File): Promise<ImportUpload> {
  const body = new FormData();
  body.append("file", file);
  return apiRequest<ImportUpload>(
    `/v1/platforms/${platformId}/service-imports`,
    { method: "POST", body },
    { authenticated: true },
  );
}

export function previewServiceImport(importId: string, mapping: ImportMapping): Promise<ImportPreview> {
  return apiRequest<ImportPreview>(
    `/v1/service-imports/${importId}/preview`,
    { method: "POST", body: JSON.stringify(mapping) },
    { authenticated: true },
  );
}

export function confirmServiceImport(
  importId: string,
  ignoredRows: number[],
  duplicateStrategy: "ignore" | "merge",
  categoryOverrides: Record<number, string>,
): Promise<ImportResult> {
  return apiRequest<ImportResult>(
    `/v1/service-imports/${importId}/confirm`,
    { method: "POST", body: JSON.stringify({ ignored_rows: ignoredRows, duplicate_strategy: duplicateStrategy, category_overrides: categoryOverrides }) },
    { authenticated: true },
  );
}
