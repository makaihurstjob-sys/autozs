const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

export type Candidate = {
  id: number;
  source: string;
  external_id: string;
  title: string;
  listing_url: string | null;
  competitor_price: number | null;
  estimated_sold: number | null;
  seller_username: string | null;
  status: string;
};

export type SupplierProduct = {
  id: number;
  supplier: string;
  source_url: string;
  last_price: number | null;
  last_shipping: number;
  in_stock: boolean;
};

export type ProductImage = {
  id: number;
  image_url: string;
  local_path: string | null;
  sort_order: number;
};

export type ListingDraft = {
  id: number;
  marketplace: string;
  title: string;
  description: string;
  source_price: number | null;
  calculated_price: number | null;
  margin_percent: number;
  ebay_fee_rate: number;
  status: string;
};

export type ListingJob = {
  id: number;
  product_id: number;
  sku: string;
  title: string;
  price: number | null;
  estimated_profit: number | null;
  meets_minimum_profit: boolean | null;
  ebay_account_key: string;
  action: string;
  status: string;
  scheduled_for: string | null;
  listing_schedule_at: string | null;
  started_at: string | null;
  completed_at: string | null;
  attempts: number;
  ebay_draft_id: string | null;
  message: string | null;
  manual_ready: boolean;
  api_ready: boolean;
  missing_manual: string[];
  missing_api: string[];
  warnings: string[];
  image_count: number;
  local_image_count: number;
  image_upload_status: string;
  source_url: string | null;
  assistant_url: string;
  updated_at: string;
  created_at: string;
};

export type Product = {
  id: number;
  sku: string;
  title: string;
  status: string;
  competitor_price: number | null;
  desired_profit: number;
  risk_buffer: number;
  undercut_amount: number;
  supplier_products: SupplierProduct[];
  images: ProductImage[];
  listing_drafts: ListingDraft[];
};

export type Snapshot = {
  id: number;
  product_id: number;
  price: number | null;
  shipping: number;
  floor_price: number | null;
  suggested_price: number | null;
  message: string | null;
  created_at: string;
};

export type Order = {
  id: number;
  ebay_order_id: string;
  buyer_username: string | null;
  status: string;
  total: number;
  ship_by: string | null;
  fulfillment_tasks: { id: number; status: string; note: string | null; exception_reason: string | null }[];
  items: { id: number; title: string; quantity: number; sale_price: number; expected_profit: number | null }[];
};

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {})
    },
    cache: "no-store"
  });
  if (!response.ok) {
    throw new Error(await response.text());
  }
  return response.json() as Promise<T>;
}

export const api = {
  createResearchJob: (source: string, query: string) =>
    request("/research/jobs", { method: "POST", body: JSON.stringify({ source, query }) }),
  listCandidates: () => request<Candidate[]>("/research/candidates"),
  approveCandidate: (id: number) => request<Product>(`/research/candidates/${id}/approve`, { method: "POST" }),
  rejectCandidate: (id: number) => request<Candidate>(`/research/candidates/${id}/reject`, { method: "POST" }),
  listProducts: () => request<Product[]>("/products"),
  listListingJobs: () => request<ListingJob[]>("/listing-jobs"),
  createListingJobs: (product_ids: number[], scheduled_for?: string | null, ebay_account_key = "manual", listing_schedule_at?: string | null) =>
    request<ListingJob[]>("/listing-jobs", {
      method: "POST",
      body: JSON.stringify({ product_ids, scheduled_for, listing_schedule_at, ebay_account_key, action: "create_draft" })
    }),
  runListingJob: (id: number) => request<{ job: ListingJob; package: unknown | null }>(`/listing-jobs/${id}/run`, { method: "POST" }),
  runNextListingJob: (ebay_account_key?: string) =>
    request<{ job: ListingJob; package: unknown | null }>(
      `/listing-jobs/next${ebay_account_key ? `?ebay_account_key=${encodeURIComponent(ebay_account_key)}` : ""}`,
      { method: "POST" }
    ),
  updateListingJob: (id: number, payload: Partial<Pick<ListingJob, "status" | "scheduled_for" | "listing_schedule_at" | "ebay_draft_id" | "message">>) =>
    request<ListingJob>(`/listing-jobs/${id}`, { method: "PATCH", body: JSON.stringify(payload) }),
  importProducts: (urls: string, source_price_override?: number, competitor_price?: number) =>
    request<{ imported: number; products: Product[]; warnings: string[] }>("/products/import", {
      method: "POST",
      body: JSON.stringify({ urls, source_price_override, competitor_price })
    }),
  attachSupplier: (id: number, source_url: string, last_price: number) =>
    request<Product>(`/products/${id}/supplier`, {
      method: "POST",
      body: JSON.stringify({ supplier: "home_depot", source_url, last_price, last_shipping: 0, in_stock: true })
    }),
  runRepricing: () => request<{ updated: number; snapshots: Snapshot[] }>("/repricing/run", { method: "POST" }),
  listSnapshots: () => request<Snapshot[]>("/repricing/snapshots"),
  syncSandboxOrder: () => request<Order>("/orders/sync-sandbox", { method: "POST" }),
  listOrders: () => request<Order[]>("/orders"),
  updateTask: (id: number, status: string) =>
    request(`/fulfillment-tasks/${id}`, { method: "PATCH", body: JSON.stringify({ status }) }),
  readSettings: () => request<Record<string, string | number | boolean>>("/settings"),
  updatePricingSettings: (payload: Record<string, number>) =>
    request<Record<string, string | number | boolean>>("/settings/pricing", {
      method: "PATCH",
      body: JSON.stringify(payload)
    })
};
