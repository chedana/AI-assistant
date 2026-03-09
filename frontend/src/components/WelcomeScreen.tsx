const EXAMPLES = [
  "2 bed flat in Hackney under £1,800",
  "Furnished studio near King's Cross",
  "3 bed house in Zone 2, pet-friendly",
  "Something with a garden in Brixton",
];

type Props = {
  onSuggestionClick: (text: string) => void;
};

export default function WelcomeScreen({ onSuggestionClick }: Props) {
  return (
    <div className="flex h-full flex-col items-center justify-center px-6 text-center">
      <div className="mb-4 text-5xl">🏠</div>
      <h2 className="text-xl font-semibold text-text">Find your next rental</h2>
      <p className="mt-2 max-w-md text-sm text-muted">
        Describe what you're looking for in the chat — I'll search thousands of
        listings and find what matches.
      </p>
      <div className="mt-8 w-full max-w-md space-y-2">
        <p className="text-xs font-medium uppercase tracking-wider text-muted">
          Try asking
        </p>
        {EXAMPLES.map((text) => (
          <button
            key={text}
            type="button"
            onClick={() => onSuggestionClick(text)}
            className="w-full rounded-lg border border-border bg-panel px-4 py-2.5 text-left text-sm text-muted transition-colors hover:border-neutral-500 hover:text-text"
          >
            &ldquo;{text}&rdquo;
          </button>
        ))}
      </div>
    </div>
  );
}
