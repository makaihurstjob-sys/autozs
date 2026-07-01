"use client";

import { useEffect, useMemo, useState } from "react";
import {
  BadgeDollarSign,
  Boxes,
  Check,
  ClipboardList,
  Play,
  RefreshCw,
  Search,
  Settings,
  ShoppingCart,
  X
} from "lucide-react";
import { api, Candidate, Order, Product, Snapshot } from "@/lib/api";

type Tab = "research" | "candidates" | "products" | "repricing" | "orders" | "settings";

export default function Dashboard() {
  const [tab, setTab] = useState<Tab>("research");
  const [source, setSource] = useState("competitor");
  const [query, setQuery] = useState("");
  const [importUrls, setImportUrls] = useState("");
  const [sourcePrice, setSourcePrice] = useState("");
  const [competitorPrice, setCompetitorPrice] = useState("");
  const [candidates, setCandidates] = useState<Candidate[]>([]);
  const [products, setProducts] = useState<Product[]>([]);
  const [snapshots, setSnapshots] = useState<Snapshot[]>([]);
  const [orders, setOrders] = useState<Order[]>([]);
  const [settings, setSettings] = useState<Record<string, string | number | boolean>>({});
  const [supplierUrls, setSupplierUrls] = useState<Record<number, string>>({});
  const [supplierPrices, setSupplierPrices] = useState<Record<number, string>>({});
  const [message, setMessage] = useState("Ready");

  const pendingCandidates = useMemo(() => candidates.filter((candidate) => candidate.status === "pending"), [candidates]);

  async function refreshAll() {
    const [candidateData, productData, snapshotData, orderData, settingsData] = await Promise.all([
      api.listCandidates(),
      api.listProducts(),
      api.listSnapshots(),
      api.listOrders(),
      api.readSettings()
    ]);
    setCandidates(candidateData);
    setProducts(productData);
    setSnapshots(snapshotData);
    setOrders(orderData);
    setSettings(settingsData);
  }

  useEffect(() => {
    refreshAll().catch((error) => setMessage(error.message));
  }, []);

  async function createResearchJob() {
    if (!query.trim()) {
      setMessage("Enter a competitor username, seed listing, or keyword.");
      return;
    }
    await api.createResearchJob(source, query.trim());
    setQuery("");
    setMessage("Research job completed and candidates were created.");
    await refreshAll();
    setTab("candidates");
  }

  async function importSourceProducts() {
    if (!importUrls.trim()) {
      setMessage("Paste at least one source URL.");
      return;
    }
    const sourceOverride = sourcePrice.trim() ? Number(sourcePrice) : undefined;
    const competitor = competitorPrice.trim() ? Number(competitorPrice) : undefined;
    const result = await api.importProducts(importUrls, sourceOverride, competitor);
    setMessage(`Imported ${result.imported} product(s). ${result.warnings.join(" ")}`);
    setImportUrls("");
    await refreshAll();
    setTab("products");
  }

  async function approveCandidate(id: number) {
    await api.approveCandidate(id);
    setMessage("Candidate approved into products.");
    await refreshAll();
  }

  async function rejectCandidate(id: number) {
    await api.rejectCandidate(id);
    setMessage("Candidate rejected.");
    await refreshAll();
  }

  async function attachSupplier(product: Product) {
    const url = supplierUrls[product.id];
    const price = Number(supplierPrices[product.id]);
    if (!url || Number.isNaN(price)) {
      setMessage("Add a supplier URL and numeric price before attaching.");
      return;
    }
    await api.attachSupplier(product.id, url, price);
    setMessage("Supplier URL attached and product moved to monitoring.");
    await refreshAll();
  }

  async function runRepricing() {
    const result = await api.runRepricing();
    setMessage(`Repricing calculated ${result.updated} product(s).`);
    await refreshAll();
    setTab("repricing");
  }

  async function syncOrders() {
    await api.syncSandboxOrder();
    setMessage("Sandbox order imported.");
    await refreshAll();
    setTab("orders");
  }

  const nav = [
    ["research", Search, "Research"],
    ["candidates", ClipboardList, "Candidates"],
    ["products", Boxes, "Products"],
    ["repricing", BadgeDollarSign, "Repricing"],
    ["orders", ShoppingCart, "Orders"],
    ["settings", Settings, "Settings"]
  ] as const;

  return (
    <main className="shell">
      <header className="topbar">
        <div className="brand">
          <img className="brand-logo" src="/assets/autozs-logo.png" alt="AutoZS" />
          <div>
            <strong>AutoZS</strong>
            <span>Home Depot to eBay automation dashboard</span>
          </div>
        </div>
        <div className="actions">
          <button className="button secondary" onClick={refreshAll} title="Refresh dashboard data">
            <RefreshCw size={16} /> Refresh
          </button>
          <button className="button" onClick={runRepricing} title="Run repricing calculations">
            <Play size={16} /> Reprice
          </button>
        </div>
      </header>

      <div className="layout">
        <aside className="sidebar">
          {nav.map(([key, Icon, label]) => (
            <button key={key} className={`nav-button ${tab === key ? "active" : ""}`} onClick={() => setTab(key)}>
              <Icon size={17} /> {label}
            </button>
          ))}
        </aside>

        <section className="main">
          <div className="metrics">
            <Metric label="Pending candidates" value={pendingCandidates.length} />
            <Metric label="Products" value={products.length} />
            <Metric label="Snapshots" value={snapshots.length} />
            <Metric label="Orders" value={orders.length} />
          </div>
          <div className="muted">{message}</div>

          {tab === "research" && (
            <Panel icon={<Search size={18} />} title="Product Research">
              <div className="form-grid" style={{ marginBottom: 14 }}>
                <textarea
                  value={importUrls}
                  onChange={(event) => setImportUrls(event.target.value)}
                  placeholder="Paste one Home Depot/source URL per line"
                  style={{ gridColumn: "1 / -1", minHeight: 100 }}
                />
                <input value={sourcePrice} onChange={(event) => setSourcePrice(event.target.value)} placeholder="Source price override" />
                <input value={competitorPrice} onChange={(event) => setCompetitorPrice(event.target.value)} placeholder="Competitor price" />
                <button className="button" onClick={importSourceProducts}>Import Product</button>
              </div>
              <div className="form-grid">
                <select value={source} onChange={(event) => setSource(event.target.value)}>
                  <option value="competitor">Competitor</option>
                  <option value="keyword">Keyword</option>
                </select>
                <input
                  value={query}
                  onChange={(event) => setQuery(event.target.value)}
                  placeholder="Seller username, seed listing URL, or keyword"
                />
                <button className="button" onClick={createResearchJob}>
                  <Search size={16} /> Scan
                </button>
              </div>
            </Panel>
          )}

          {tab === "candidates" && (
            <Panel icon={<ClipboardList size={18} />} title="Candidate Review">
              <DataTable
                headers={["Title", "Source", "Price", "Sold", "Status", "Actions"]}
                rows={candidates.map((candidate) => [
                  candidate.title,
                  candidate.source,
                  money(candidate.competitor_price),
                  candidate.estimated_sold ?? "-",
                  <Status key="status" value={candidate.status} />,
                  <div className="actions" key="actions">
                    <button className="button" onClick={() => approveCandidate(candidate.id)} title="Approve candidate">
                      <Check size={15} /> Approve
                    </button>
                    <button className="button danger" onClick={() => rejectCandidate(candidate.id)} title="Reject candidate">
                      <X size={15} /> Reject
                    </button>
                  </div>
                ])}
              />
            </Panel>
          )}

          {tab === "products" && (
            <Panel icon={<Boxes size={18} />} title="Products">
              <DataTable
                headers={["SKU", "Title", "Competitor", "Supplier", "Status"]}
                rows={products.map((product) => [
                  product.sku,
                  product.title,
                  money(product.competitor_price),
                  product.supplier_products.length ? (
                    <div key="attached">
                      <span className="status">Attached</span>
                      {product.listing_drafts[0]?.calculated_price ? <div className="muted">Draft: {money(product.listing_drafts[0].calculated_price)}</div> : null}
                      <div className="muted">{product.images.length} image URL(s)</div>
                    </div>
                  ) : (
                    <div key="attach">
                      <span className="status warn">Missing supplier</span>
                      <div className="attach-grid">
                        <input
                          placeholder="Home Depot example URL"
                          value={supplierUrls[product.id] ?? ""}
                          onChange={(event) => setSupplierUrls({ ...supplierUrls, [product.id]: event.target.value })}
                        />
                        <input
                          placeholder="Price"
                          value={supplierPrices[product.id] ?? ""}
                          onChange={(event) => setSupplierPrices({ ...supplierPrices, [product.id]: event.target.value })}
                        />
                        <button className="button" onClick={() => attachSupplier(product)}>
                          Attach
                        </button>
                      </div>
                    </div>
                  ),
                  <Status key="status" value={product.status} />
                ])}
              />
            </Panel>
          )}

          {tab === "repricing" && (
            <Panel icon={<BadgeDollarSign size={18} />} title="Repricing">
              <DataTable
                headers={["Product", "Supplier", "Floor", "Suggested", "Decision", "Created"]}
                rows={snapshots.map((snapshot) => [
                  snapshot.product_id,
                  money(snapshot.price),
                  money(snapshot.floor_price),
                  money(snapshot.suggested_price),
                  snapshot.message ?? "-",
                  new Date(snapshot.created_at).toLocaleString()
                ])}
              />
            </Panel>
          )}

          {tab === "orders" && (
            <Panel icon={<ShoppingCart size={18} />} title="Orders">
              <button className="button" onClick={syncOrders}>
                <RefreshCw size={16} /> Import Sandbox Orders
              </button>
              <DataTable
                headers={["Order", "Buyer", "Total", "Ship by", "Items", "Task"]}
                rows={orders.map((order) => [
                  order.ebay_order_id,
                  order.buyer_username ?? "-",
                  money(order.total),
                  order.ship_by ? new Date(order.ship_by).toLocaleDateString() : "-",
                  order.items.map((item) => item.title).join(", "),
                  order.fulfillment_tasks[0] ? (
                    <select
                      key="task"
                      value={order.fulfillment_tasks[0].status}
                      onChange={async (event) => {
                        await api.updateTask(order.fulfillment_tasks[0].id, event.target.value);
                        await refreshAll();
                      }}
                    >
                      <option value="open">Open</option>
                      <option value="in_progress">In progress</option>
                      <option value="completed">Completed</option>
                      <option value="blocked">Blocked</option>
                    </select>
                  ) : (
                    "-"
                  )
                ])}
              />
            </Panel>
          )}

          {tab === "settings" && (
            <Panel icon={<Settings size={18} />} title="Settings">
              <DataTable headers={["Setting", "Value"]} rows={Object.entries(settings)} />
            </Panel>
          )}
        </section>
      </div>
    </main>
  );
}

function Metric({ label, value }: { label: string; value: number }) {
  return (
    <div className="metric">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function Panel({ icon, title, children }: { icon: React.ReactNode; title: string; children: React.ReactNode }) {
  return (
    <section className="panel">
      <div className="panel-header">
        <div className="panel-title">
          {icon} {title}
        </div>
      </div>
      <div className="panel-body">{children}</div>
    </section>
  );
}

function DataTable({ headers, rows }: { headers: string[]; rows: React.ReactNode[][] }) {
  if (!rows.length) {
    return <p className="muted">No records yet.</p>;
  }
  return (
    <table>
      <thead>
        <tr>
          {headers.map((header) => (
            <th key={header}>{header}</th>
          ))}
        </tr>
      </thead>
      <tbody>
        {rows.map((row, rowIndex) => (
          <tr key={rowIndex}>
            {row.map((cell, cellIndex) => (
              <td key={cellIndex}>{cell}</td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function Status({ value }: { value: string }) {
  return <span className={`status ${value === "pending" || value === "draft" ? "warn" : ""}`}>{value}</span>;
}

function money(value: number | null | undefined) {
  if (value === null || value === undefined) {
    return "-";
  }
  return `$${value.toFixed(2)}`;
}
