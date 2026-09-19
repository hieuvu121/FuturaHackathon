import Link from "next/link";

const LINKS = [
  ["/connect", "Connect repositories"],
  ["/profile", "Capability profile"],
  ["/recall", "Revision loop"],
  ["/roadmap", "Roadmap"],
  ["/share/1", "Public profile"],
];

export default function Home() {
  return (
    <main className="mx-auto max-w-xl space-y-4 p-12">
      <h1 className="text-2xl font-medium">Futura</h1>
      <p className="text-sm text-neutral-600">A capability profile evidenced by your own code.</p>
      <ul className="space-y-2">
        {LINKS.map(([href, label]) => (
          <li key={href}>
            <Link href={href} className="text-blue-700 underline underline-offset-2">{label}</Link>
          </li>
        ))}
      </ul>
    </main>
  );
}
