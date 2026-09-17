import type { SVGProps } from 'react';

export function TotalEnergiesIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 28 22" fill="none" aria-hidden="true" {...props}>
      <path
        fill="url(#te-a)"
        d="M15.417 9.848c-.871.694-1.706 1.613-2.19 2.617-.996 2.066-.444 3.965-.017 5.197.58 1.677 1.758 2.524 3.161 3.143 2 .882 4.515.942 6.798.352.805-.208 2.054-.64 2.327-1.043.295-.437.342-1.28-.293-1.652-.618-.361-.678-.085-2.521.324-1.282.285-2.683.334-4.365-.392-1.06-.458-1.779-1.16-2.024-2.12-.703-2.756.817-3.778 1.113-3.964z"
      />
      <path
        fill="url(#te-b)"
        d="M17.513 13.092c-.792-.105-3.115-.351-5.546-.782-3.76-.668-8.182-1.593-9.594-1.692-2.717-.19-3.17 3.34-1.001 3.943 1.228.342 4.608-.017 5.43 1.605.25.494.912 2.357 1.662 4.664.294.905 2.685.763 2.24-1.164-.253-1.1-.831-4.073-.831-4.073s6.858.727 7.416.775z"
      />
      <path
        fill="url(#te-c)"
        d="M21.124 11.277c.871.023 2.387.247 3.07.703l3.805.75c.036-2.112-1.122-3.249-2.42-3.904-.986-.497-2.368-.902-4.442-.814-1.984.085-4.07.52-5.733 1.845l1.988 2.465c.938-.59 2.117-1.088 3.732-1.045"
      />
      <path fill="url(#te-d)" d="M24.133 11.941s.2.129.287.208c.415.379.552.831-.706 1.04l.995 3.075c2.263-.606 3.262-1.942 3.29-3.572z" />
      <path fill="url(#te-e)" d="M23.752 13.183c-1.115.185-3.276.304-6.256-.091l-.224 3.276c4.839.419 6.54.133 7.474-.117z" />
      <defs>
        <linearGradient id="te-a" x1={15.789} x2={23.069} y1={12.11} y2={20.016} gradientUnits="userSpaceOnUse">
          <stop stopColor="#0186F5" />
          <stop offset={0.315} stopColor="#35C2B0" />
          <stop offset={0.667} stopColor="#AAD825" />
          <stop offset={1} stopColor="#FED700" />
        </linearGradient>
        <linearGradient id="te-b" x1={9.813} x2={9.873} y1={20.555} y2={15.593} gradientUnits="userSpaceOnUse">
          <stop stopColor="#FF7F00" />
          <stop offset={1} stopColor="#FE0201" />
        </linearGradient>
        <linearGradient id="te-c" x1={15.983} x2={24.02} y1={10.871} y2={11.025} gradientUnits="userSpaceOnUse">
          <stop stopColor="#0186F5" />
          <stop offset={1} stopColor="#3156FD" />
        </linearGradient>
        <linearGradient id="te-d" x1={24.46} x2={25.201} y1={13.896} y2={12.434} gradientUnits="userSpaceOnUse">
          <stop stopColor="#8434D5" />
          <stop offset={1} stopColor="#3156FD" />
        </linearGradient>
        <linearGradient id="te-e" x1={23.635} x2={17.464} y1={14.711} y2={15.003} gradientUnits="userSpaceOnUse">
          <stop stopColor="#8434D5" />
          <stop offset={1} stopColor="#FE0201" />
        </linearGradient>
      </defs>
    </svg>
  );
}
