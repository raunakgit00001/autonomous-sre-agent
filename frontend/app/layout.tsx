import './globals.css';
import type { Metadata } from 'next';

export const metadata: Metadata = {
  title: 'Autonomous SRE Agent — Control Center',
  description: 'AI-driven infrastructure incident detection, vector postmortem retrieval, confidence-gated autonomy & Slack human approval loop.',
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <head>
        <meta name="viewport" content="width=device-width, initial-scale=1" />
      </head>
      <body className="antialiased bg-[#090d16] text-slate-100 min-h-screen">
        {children}
      </body>
    </html>
  );
}
