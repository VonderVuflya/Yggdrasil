import type { Language } from "../lib/i18n";
// Local SVGs stay sharp and do not depend on platform emoji fonts or a CDN.
export function LanguageFlag({ language }: { language: Language }) {
  return (
    <svg
      viewBox="0 0 28 20"
      width="23"
      height="16"
      className="language-flag"
      aria-hidden="true"
    >
      {language === "en" ? (
        <>
          <path fill="#234477" d="M0 0h28v20H0z" />
          <path stroke="#fff" strokeWidth="5" d="m0 0 28 20M28 0 0 20" />
          <path stroke="#c73947" strokeWidth="2" d="m0 0 28 20M28 0 0 20" />
          <path stroke="#fff" strokeWidth="8" d="M14 0v20M0 10h28" />
          <path stroke="#c73947" strokeWidth="4" d="M14 0v20M0 10h28" />
        </>
      ) : language === "ru" ? (
        <>
          <path fill="#fff" d="M0 0h28v20H0z" />
          <path fill="#3158a5" d="M0 6.67h28v6.66H0z" />
          <path fill="#d5474e" d="M0 13.33h28V20H0z" />
        </>
      ) : language === "de" ? (
        <>
          <path fill="#252525" d="M0 0h28v20H0z" />
          <path fill="#c83b3b" d="M0 6.67h28v6.66H0z" />
          <path fill="#efc444" d="M0 13.33h28V20H0z" />
        </>
      ) : language === "es" ? (
        <>
          <path fill="#bd303d" d="M0 0h28v20H0z" />
          <path fill="#f5c748" d="M0 5h28v10H0z" />
          <path fill="#bd303d" d="M7 8h4v5H7z" />
        </>
      ) : language === "fr" ? (
        <>
          <path fill="#fff" d="M0 0h28v20H0z" />
          <path fill="#3157a1" d="M0 0h9.33v20H0z" />
          <path fill="#dc4b52" d="M18.67 0H28v20h-9.33z" />
        </>
      ) : language === "ja" ? (
        <>
          <path fill="#fff" d="M0 0h28v20H0z" />
          <circle fill="#bc3548" cx="14" cy="10" r="5" />
        </>
      ) : (
        <>
          <path fill="#ce3737" d="M0 0h28v20H0z" />
          <path fill="#f6d35b" d="m6 3 1 3h3L7.5 8l1 3L6 9l-2.5 2 1-3L2 6h3z" />
          <g fill="#f6d35b">
            {[
              [12, 3],
              [15, 5],
              [15, 9],
              [12, 12],
            ].map(([x, y]) => (
              <path
                key={`${x}-${y}`}
                transform={`translate(${x} ${y})`}
                d="m0 -1.2 .3 .8 .9 .1 -.7 .6 .3 .9 -.8 -.5 -.8 .5 .3 -.9 -.7 -.6 .9 -.1z"
              />
            ))}
          </g>
        </>
      )}
    </svg>
  );
}
