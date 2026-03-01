import { useEffect, useMemo, useRef } from "react";
import type { ChatSession, SessionMetadata } from "../types/chat";
import CompareTable from "./CompareTable";
import ConstraintTags from "./ConstraintTags";
import ListingCard from "./ListingCard";
import MessageBubble from "./MessageBubble";
import QuickReplies from "./QuickReplies";

type Props = {
  session: ChatSession | undefined;
  isGenerating: boolean;
  metadata: SessionMetadata | null;
  suppressedIds: Set<string>;
  metadataForId: string | null;
  activeAssistantId: string | null;
  onQuickReply: (text: string, routeHint?: Record<string, unknown>) => void;
  onSaveListing?: (pageIndex: number) => void;
};

export default function ChatArea({
  session,
  isGenerating,
  metadata,
  suppressedIds,
  metadataForId,
  activeAssistantId,
  onQuickReply,
  onSaveListing,
}: Props) {
  const endRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [session?.messages.length, isGenerating, metadata]);

  const savedIds = useMemo(
    () => new Set(metadata?.shortlist?.saved_ids ?? []),
    [metadata?.shortlist?.saved_ids],
  );

  const showConstraints = metadata?.constraints && Object.keys(metadata.constraints).length > 0;
  const showCompare = !!(metadata?.compare_data && metadata.compare_data.listings.length >= 2);
  const showListings = !!(metadata?.search_results && metadata.search_results.listings.length > 0);
  const showQuickReplies = !isGenerating && !!(metadata?.quick_replies && metadata.quick_replies.length > 0);

  return (
    <section className="relative flex-1 overflow-y-auto">
      {showConstraints && (
        <ConstraintTags
          constraints={metadata!.constraints!}
          onRemove={onQuickReply}
        />
      )}

      <div className="px-4 py-4">
        <div className="mx-auto max-w-3xl space-y-4">
          {session?.messages.length ? (
            <>
              {session.messages.map((message) => {
                // Old suppressed messages (previous search pages, old compares):
                // fully hidden, their slot replaced by nothing.
                if (suppressedIds.has(message.id) && message.id !== metadataForId) {
                  return null;
                }

                // Current structured position: render cards/compare inline here
                // instead of the assistant text bubble, so they appear naturally
                // in the conversation flow rather than pinned to the bottom.
                if (message.id === metadataForId) {
                  return (
                    <div key={message.id} className="space-y-3">
                      {showCompare && <CompareTable data={metadata!.compare_data!} />}
                      {showListings && (
                        <div className="space-y-3">
                          {metadata!.search_results!.listings.map((listing, idx) => (
                            <ListingCard
                              key={listing.url || idx}
                              listing={listing}
                              isSaved={savedIds.has(listing.url)}
                              onSave={onSaveListing ? () => onSaveListing(idx + 1) : undefined}
                            />
                          ))}
                          {metadata!.search_results!.has_more && (
                            <button
                              onClick={() => onQuickReply("show me more", { intent: "Page_Nav", page_action: "next" })}
                              className="w-full rounded-lg border border-border py-2 text-xs text-muted hover:bg-neutral-800 hover:text-text"
                            >
                              Show more results ({metadata!.search_results!.total - metadata!.search_results!.listings.length * (metadata!.search_results!.page_index + 1)} remaining)
                            </button>
                          )}
                        </div>
                      )}
                    </div>
                  );
                }

                return (
                  <MessageBubble
                    key={message.id}
                    message={message}
                    isGenerating={isGenerating}
                    isActive={message.id === activeAssistantId}
                  />
                );
              })}

              {showQuickReplies && (
                <QuickReplies
                  replies={metadata!.quick_replies!}
                  onSelect={onQuickReply}
                />
              )}
            </>
          ) : (
            <div className="pt-16 text-center text-sm text-muted">
              Start a conversation.
            </div>
          )}
          <div ref={endRef} />
        </div>
      </div>
    </section>
  );
}
