import React from 'react';

export const metadata = {
  title: 'PolySignal',
  description: 'Market Intelligence Dashboard',
}

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <html lang="en">
      <body style={{ margin: 0, backgroundColor: '#0a0e27', color: 'white' }}>
        {children}
      </body>
    </html>
  )
}
