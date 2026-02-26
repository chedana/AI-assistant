import { markdownToHtml } from "../lib/markdown";
import type { Role } from "../types/chat";

const URL_REGEX = /(https?:\/\/[^\s]+)/g;
const URL_MATCH_REGEX = /^https?:\/\/[^\s]+$/;

/** Plain text with clickable URLs (for user messages) */
function renderPlainText(content: string) {
  const lines = content.split("\n");
  return lines.map((line, lineIndex) => {
    const parts = line.split(URL_REGEX);
    return (
      <span key={lineIndex}>
        {parts.map((part, partIndex) => {
          if (URL_MATCH_REGEX.test(part)) {
            return (
              <a
                key={partIndex}
                href={part}
                target="_blank"
                rel="noopener noreferrer"
                className="underline text-[#7dd3fc]"
              >
                {part}
              </a>
            );
          }
          return <span key={partIndex}>{part}</span>;
        })}
        {lineIndex < lines.length - 1 ? <br /> : null}
      </span>
    );
  });
}

type Props = {
  content: string;
  role: Role;
};

export default function MessageContent({ content, role }: Props) {
  if (role === "user") {
    return <>{renderPlainText(content)}</>;
  }

  // Assistant: render as Markdown
  const html = markdownToHtml(content);
  return (
    <div
      className="markdown-content"
      dangerouslySetInnerHTML={{ __html: html }}
    />
  );
}
