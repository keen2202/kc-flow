import { useState, useEffect, useCallback } from "react";
import { Search, Star, Download, Package, Puzzle, Wrench, ChevronRight, X, ExternalLink, Shield } from "lucide-react";
import axios from "axios";

interface PackageItem {
  package_id: string;
  name: string;
  display_name: string;
  description: string;
  type: "node" | "skill" | "plugin";
  author: string;
  category: string;
  tags: string[];
  icon: string;
  current_version: string;
  total_downloads: number;
  avg_rating: number;
  review_count: number;
  verified: boolean;
  repository?: string;
  homepage?: string;
  versions: { version: string; changelog: string; published_at: string }[];
  reviews?: { review_id: string; user_id: string; rating: number; title: string; comment: string; created_at: string }[];
}

const TYPE_ICONS = { node: Wrench, skill: Package, plugin: Puzzle };
const TYPE_COLORS = {
  node: "bg-emerald-100 text-emerald-700",
  skill: "bg-blue-100 text-blue-700",
  plugin: "bg-purple-100 text-purple-700",
};
const RATING_LABELS = ["", "Poor", "Fair", "Good", "Very Good", "Excellent"];

export function MarketplaceView() {
  const [packages, setPackages] = useState<PackageItem[]>([]);
  const [search, setSearch] = useState("");
  const [typeFilter, setTypeFilter] = useState<string>("");
  const [categoryFilter, setCategoryFilter] = useState("");
  const [categories, setCategories] = useState<{ name: string; count: number }[]>([]);
  const [sort, setSort] = useState("downloads");
  const [selectedPkg, setSelectedPkg] = useState<PackageItem | null>(null);
  const [loading, setLoading] = useState(false);

  const fetchPackages = useCallback(async () => {
    setLoading(true);
    try {
      const params: Record<string, string | number> = { sort, page: 1, page_size: 50 };
      if (search) params.q = search;
      if (typeFilter) params.type = typeFilter;
      if (categoryFilter) params.category = categoryFilter;
      const { data } = await axios.get("/api/marketplace/search", { params });
      if (data.code === 0) setPackages(data.data.items);
    } catch {
      // fallback: empty
    }
    setLoading(false);
  }, [search, typeFilter, categoryFilter, sort]);

  const fetchCategories = useCallback(async () => {
    try {
      const { data } = await axios.get("/api/marketplace/categories");
      if (data.code === 0) setCategories(data.data);
    } catch { /* ignore */ }
  }, []);

  useEffect(() => { fetchPackages(); }, [fetchPackages]);
  useEffect(() => { fetchCategories(); }, [fetchCategories]);

  const fetchDetail = async (name: string) => {
    try {
      const { data } = await axios.get(`/api/marketplace/package/${name}`);
      if (data.code === 0) setSelectedPkg(data.data);
    } catch { /* ignore */ }
  };

  const installPkg = async (name: string) => {
    try {
      await axios.post(`/api/marketplace/install/${name}`);
      fetchPackages();
    } catch { /* ignore */ }
  };

  const formatNumber = (n: number) => {
    if (n >= 1000) return `${(n / 1000).toFixed(1)}k`;
    return n.toString();
  };

  return (
    <div className="flex h-full">
      {/* Sidebar */}
      <div className="w-56 border-r bg-white p-4 flex flex-col gap-4 overflow-y-auto">
        <h3 className="text-xs font-semibold text-gray-400 uppercase tracking-wider">Categories</h3>
        <button
          onClick={() => setCategoryFilter("")}
          className={`text-left text-sm px-2 py-1.5 rounded ${!categoryFilter ? "bg-blue-50 text-blue-700 font-medium" : "text-gray-600 hover:bg-gray-50"}`}
        >
          All Packages
        </button>
        {categories.map((c) => (
          <button
            key={c.name}
            onClick={() => setCategoryFilter(c.name)}
            className={`text-left text-sm px-2 py-1.5 rounded flex justify-between ${categoryFilter === c.name ? "bg-blue-50 text-blue-700 font-medium" : "text-gray-600 hover:bg-gray-50"}`}
          >
            <span>{c.name}</span>
            <span className="text-gray-400 text-xs">{c.count}</span>
          </button>
        ))}
      </div>

      {/* Main */}
      <div className="flex-1 flex flex-col overflow-hidden">
        {/* Search bar */}
        <div className="border-b bg-white p-4 flex items-center gap-3">
          <div className="flex-1 relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
            <input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search packages..."
              className="w-full pl-9 pr-3 py-2 border rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
          </div>
          {(["node", "skill", "plugin"] as const).map((t) => {
            const Icon = TYPE_ICONS[t];
            return (
              <button
                key={t}
                onClick={() => setTypeFilter(typeFilter === t ? "" : t)}
                className={`flex items-center gap-1.5 px-3 py-2 rounded-lg text-sm border ${typeFilter === t ? "bg-blue-50 border-blue-300 text-blue-700" : "bg-white border-gray-200 text-gray-600 hover:border-gray-300"}`}
              >
                <Icon className="w-4 h-4" />
                <span className="capitalize">{t}s</span>
              </button>
            );
          })}
          <select
            value={sort}
            onChange={(e) => setSort(e.target.value)}
            className="border rounded-lg px-3 py-2 text-sm text-gray-600"
          >
            <option value="downloads">Most Downloads</option>
            <option value="rating">Highest Rated</option>
            <option value="newest">Newest</option>
            <option value="name">Name</option>
          </select>
        </div>

        {/* Package grid */}
        <div className="flex-1 overflow-y-auto p-6">
          {loading ? (
            <div className="flex items-center justify-center h-40 text-gray-400">Loading...</div>
          ) : packages.length === 0 ? (
            <div className="flex flex-col items-center justify-center h-40 text-gray-400">
              <Package className="w-10 h-10 mb-2" />
              <span>No packages found</span>
            </div>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
              {packages.map((pkg) => {
                const TypeIcon = TYPE_ICONS[pkg.type];
                return (
                  <div
                    key={pkg.name}
                    onClick={() => fetchDetail(pkg.name)}
                    className="bg-white border rounded-xl p-4 hover:shadow-md transition-shadow cursor-pointer group"
                  >
                    <div className="flex items-start gap-3 mb-3">
                      <div className={`w-10 h-10 rounded-lg flex items-center justify-center ${TYPE_COLORS[pkg.type]}`}>
                        <TypeIcon className="w-5 h-5" />
                      </div>
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2">
                          <h3 className="font-semibold text-gray-900 truncate">{pkg.display_name}</h3>
                          {pkg.verified && <Shield className="w-4 h-4 text-blue-500 flex-shrink-0" />}
                        </div>
                        <p className="text-xs text-gray-400">{pkg.author}</p>
                      </div>
                    </div>
                    <p className="text-sm text-gray-600 line-clamp-2 mb-3">{pkg.description}</p>
                    <div className="flex items-center gap-3 text-xs text-gray-400">
                      <span className="flex items-center gap-1">
                        <Star className="w-3 h-3 fill-yellow-400 text-yellow-400" />
                        {pkg.avg_rating.toFixed(1)}
                      </span>
                      <span className="flex items-center gap-1">
                        <Download className="w-3 h-3" />
                        {formatNumber(pkg.total_downloads)}
                      </span>
                      <span className={`px-1.5 py-0.5 rounded text-xs ${TYPE_COLORS[pkg.type]}`}>
                        {pkg.type}
                      </span>
                      <span className="ml-auto text-gray-300 group-hover:text-blue-500 transition-colors">
                        <ChevronRight className="w-4 h-4" />
                      </span>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      </div>

      {/* Detail panel */}
      {selectedPkg && (
        <div className="w-96 border-l bg-white flex flex-col overflow-hidden">
          <div className="p-4 border-b flex items-center justify-between">
            <h2 className="font-semibold text-gray-900">{selectedPkg.display_name}</h2>
            <button onClick={() => setSelectedPkg(null)} className="text-gray-400 hover:text-gray-600">
              <X className="w-5 h-5" />
            </button>
          </div>
          <div className="flex-1 overflow-y-auto p-4 space-y-4">
            <div className="flex items-center gap-2">
              <span className={`px-2 py-0.5 rounded text-xs font-medium ${TYPE_COLORS[selectedPkg.type]}`}>
                {selectedPkg.type}
              </span>
              <span className="text-xs text-gray-400">v{selectedPkg.current_version}</span>
              {selectedPkg.verified && (
                <span className="flex items-center gap-1 text-xs text-blue-600">
                  <Shield className="w-3 h-3" /> Verified
                </span>
              )}
            </div>
            <p className="text-sm text-gray-600">{selectedPkg.description}</p>
            <div className="flex items-center gap-4 text-sm text-gray-500">
              <span className="flex items-center gap-1">
                <Star className="w-4 h-4 fill-yellow-400 text-yellow-400" />
                {selectedPkg.avg_rating.toFixed(1)} ({selectedPkg.review_count} reviews)
              </span>
              <span className="flex items-center gap-1">
                <Download className="w-4 h-4" />
                {formatNumber(selectedPkg.total_downloads)}
              </span>
            </div>
            <div className="flex flex-wrap gap-1.5">
              {selectedPkg.tags.map((t) => (
                <span key={t} className="px-2 py-0.5 bg-gray-100 text-gray-600 rounded text-xs">{t}</span>
              ))}
            </div>
            <div className="text-sm text-gray-500">
              <span className="font-medium text-gray-700">Author:</span> {selectedPkg.author}
            </div>
            <div className="text-sm text-gray-500">
              <span className="font-medium text-gray-700">Category:</span> {selectedPkg.category}
            </div>

            {/* Versions */}
            <div>
              <h4 className="text-sm font-medium text-gray-700 mb-2">Versions</h4>
              <div className="space-y-2">
                {selectedPkg.versions.slice().reverse().map((v) => (
                  <div key={v.version} className="text-xs border rounded-lg p-2">
                    <div className="flex justify-between text-gray-500">
                      <span className="font-mono font-medium">v{v.version}</span>
                      <span>{new Date(v.published_at).toLocaleDateString()}</span>
                    </div>
                    {v.changelog && <p className="text-gray-600 mt-1">{v.changelog}</p>}
                  </div>
                ))}
              </div>
            </div>

            {/* Reviews */}
            {selectedPkg.reviews && selectedPkg.reviews.length > 0 && (
              <div>
                <h4 className="text-sm font-medium text-gray-700 mb-2">Reviews</h4>
                <div className="space-y-2">
                  {selectedPkg.reviews.map((r) => (
                    <div key={r.review_id} className="text-xs border rounded-lg p-2">
                      <div className="flex items-center gap-2 mb-1">
                        <div className="flex">
                          {[1, 2, 3, 4, 5].map((s) => (
                            <Star key={s} className={`w-3 h-3 ${s <= r.rating ? "fill-yellow-400 text-yellow-400" : "text-gray-200"}`} />
                          ))}
                        </div>
                        <span className="font-medium text-gray-700">{RATING_LABELS[r.rating]}</span>
                        <span className="text-gray-400 ml-auto">{r.user_id}</span>
                      </div>
                      {r.title && <p className="font-medium text-gray-700">{r.title}</p>}
                      {r.comment && <p className="text-gray-600">{r.comment}</p>}
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Action buttons */}
            <div className="flex gap-2 pt-2">
              <button
                onClick={() => installPkg(selectedPkg.name)}
                className="flex-1 bg-blue-600 text-white py-2 rounded-lg text-sm font-medium hover:bg-blue-700 transition-colors"
              >
                Install
              </button>
              {selectedPkg.repository && (
                <a
                  href={selectedPkg.repository}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="px-3 py-2 border rounded-lg text-gray-600 hover:bg-gray-50 transition-colors"
                >
                  <ExternalLink className="w-4 h-4" />
                </a>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
