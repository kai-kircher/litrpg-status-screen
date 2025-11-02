import type { Metadata } from 'next';
import './globals.css';

export const metadata: Metadata = {
  title: 'Wandering Inn Tracker',
  description: 'Track character progression in The Wandering Inn',
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
