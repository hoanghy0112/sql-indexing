import type { Metadata } from 'next'
import { Inter } from 'next/font/google'
import './globals.css'
import { Providers } from './providers'
import { Toaster } from '@/components/ui/toaster'

const inter = Inter({
    subsets: ['latin'],
    display: 'swap',
    variable: '--font-inter',
})

export const metadata: Metadata = {
    title: 'SQL Index - Database RAG Platform',
    description: 'Connect databases, analyze schemas with AI, and chat with your data',
}

export default function RootLayout({
    children,
}: {
    children: React.ReactNode
}) {
    return (
        <html lang="en" suppressHydrationWarning>
            <body className={`${inter.className} antialiased`}>
                <Providers>
                    {children}
                    <Toaster />
                </Providers>
            </body>
        </html>
    )
}
