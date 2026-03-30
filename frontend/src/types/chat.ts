export type Role = "user" | "assistant";

export type Message = {
  id: string;
  role: Role;
  content: string;
  createdAt: number;
};

export type ChatSession = {
  id: string;
  title: string;
  createdAt: number;
  updatedAt: number;
  messages: Message[];
  thinkingMode?: "quick" | "deep";
};

// --- Metadata types (from backend SSE metadata event) ---

export type ListingData = {
  title: string;
  url: string;
  image_url: string;
  image_urls?: string[];
  address?: string;
  price_pcm: number;
  bedrooms: number;
  bathrooms: number;
  available_from?: string;
  description?: string;
  features?: string[];
  property_type?: string;
  furnish_type?: string;
  deposit?: number | null;
  size_sqm?: number | null;
  lat?: number | null;
  lon?: number | null;
  final_score?: number;
  match_pct?: number;
  penalty_reasons?: string[];
  preference_hits?: string[];
  red_flags?: string[];
  source_site?: string;
  openrent_url?: string;
  commute_time_minutes?: number | null;
  commute_summary?: string | null;
};

export type SearchResultsMeta = {
  listings: ListingData[];
  all_listings?: ListingData[];
  page_index: number;
  has_more: boolean;
  total: number;
  remaining: number;
};

export type ConstraintsMeta = Record<string, unknown>;

export type QuickReply = {
  label: string;
  text: string;
  route_hint?: Record<string, unknown>;
};

export type CompareListingData = ListingData & {
  index: number;
};

export type CompareData = {
  listings: CompareListingData[];
};

export type ShortlistMeta = {
  count: number;
  saved_ids: string[];
  listings: ListingData[];
};

export type SessionMetadata = {
  search_results?: SearchResultsMeta;
  constraints?: ConstraintsMeta;
  quick_replies?: QuickReply[];
  compare_data?: CompareData;
  shortlist?: ShortlistMeta;
  thinking_mode?: "quick" | "deep";
};
