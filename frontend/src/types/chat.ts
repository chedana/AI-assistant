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
};

// --- Metadata types (from backend SSE metadata event) ---

export type ListingData = {
  title: string;
  url: string;
  address: string;
  price_pcm: number;
  bedrooms: number;
  bathrooms: number;
  available_from: string;
  final_score: number;
  penalty_reasons: string[];
  preference_hits: string[];
};

export type SearchResultsMeta = {
  listings: ListingData[];
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

export type CompareListingData = {
  index: number;
  title: string;
  url: string;
  price_pcm: number;
  bedrooms: number;
  bathrooms: number;
  deposit: number;
  available_from: string;
  size_sqm: number;
  furnish_type: string;
  property_type: string;
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
};
