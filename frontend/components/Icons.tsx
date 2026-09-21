import type { SVGProps } from "react";

type IconProps = SVGProps<SVGSVGElement>;

function IconBase({ children, ...props }: IconProps) {
  return (
    <svg aria-hidden="true" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" {...props}>
      {children}
    </svg>
  );
}

export function StartIcon(props: IconProps) {
  return <IconBase {...props}><circle cx="12" cy="12" r="9" /><path d="m10 8.5 5.5 3.5-5.5 3.5z" /></IconBase>;
}

export function ConnectIcon(props: IconProps) {
  return <IconBase {...props}><path d="M9.5 14.5 14.5 9.5" /><path d="m7.2 16.8-1.3 1.3a3.5 3.5 0 0 1-5-5l3.7-3.7a3.5 3.5 0 0 1 5 0" /><path d="m16.8 7.2 1.3-1.3a3.5 3.5 0 1 0-5-5L9.4 4.6a3.5 3.5 0 0 0 0 5" /></IconBase>;
}

export function ProfileIcon(props: IconProps) {
  return <IconBase {...props}><path d="m12 2 8.5 5v10L12 22l-8.5-5V7L12 2Z" /><path d="m12 7 4.2 2.5v5L12 17l-4.2-2.5v-5L12 7Z" /></IconBase>;
}

export function RecallIcon(props: IconProps) {
  return <IconBase {...props}><path d="M4 4v5h5" /><path d="M5.8 17.3A8 8 0 1 0 4.2 9" /></IconBase>;
}

export function RoadmapIcon(props: IconProps) {
  return <IconBase {...props}><path d="M4 6h8" /><path d="M4 12h14" /><path d="M4 18h6" /></IconBase>;
}

export function ShareIcon(props: IconProps) {
  return <IconBase {...props}><path d="M12 16V3" /><path d="m7 8 5-5 5 5" /><path d="M5 13v7h14v-7" /></IconBase>;
}

export function CommunityIcon(props: IconProps) {
  return <IconBase {...props}><circle cx="9" cy="8" r="3.2" /><path d="M2.8 19.5c.6-3.4 3-5.2 6.2-5.2s5.6 1.8 6.2 5.2" /><path d="M16 5.2a3 3 0 0 1 0 5.6" /><path d="M18 14.6c1.8.6 2.9 2.2 3.2 4.9" /></IconBase>;
}

export function CheckIcon(props: IconProps) {
  return <IconBase {...props}><path d="m5 12 4 4L19 6" /></IconBase>;
}

export function ArrowRightIcon(props: IconProps) {
  return <IconBase {...props}><path d="M5 12h14" /><path d="m14 7 5 5-5 5" /></IconBase>;
}

export function ExternalIcon(props: IconProps) {
  return <IconBase {...props}><path d="M8 16 16 8" /><path d="M9 8h7v7" /></IconBase>;
}

export function InfoIcon(props: IconProps) {
  return <IconBase {...props}><circle cx="12" cy="12" r="9" /><path d="M12 11v5" /><path d="M12 8h.01" /></IconBase>;
}

export function CopyIcon(props: IconProps) {
  return <IconBase {...props}><rect x="8" y="8" width="11" height="11" rx="2" /><path d="M16 8V6a2 2 0 0 0-2-2H6a2 2 0 0 0-2 2v8a2 2 0 0 0 2 2h2" /></IconBase>;
}

