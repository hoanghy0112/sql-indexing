'use client'

import { useEffect, useState } from 'react'
import { useParams } from 'next/navigation'
import { useQuery } from '@tanstack/react-query'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { chatApi } from '@/lib/api'
import { cn, formatDateTime } from '@/lib/utils'
import { Database, MessageSquare, Loader2 } from 'lucide-react'

interface Message {
    id: number
    role: 'user' | 'assistant'
    content: string
    sql?: string
    data?: any[]
    created_at: string
}

export default function PublicChatPage() {
    const params = useParams()
    const shareToken = params.token as string

    // Fetch public chat
    const { data: chat, isLoading, error } = useQuery({
        queryKey: ['public-chat', shareToken],
        queryFn: async () => {
            const response = await chatApi.getPublicChat(shareToken)
            return response.data
        },
        enabled: !!shareToken,
    })

    if (isLoading) {
        return (
            <div className="min-h-screen flex items-center justify-center bg-background">
                <Loader2 className="h-8 w-8 animate-spin text-primary" />
            </div>
        )
    }

    if (error || !chat) {
        return (
            <div className="min-h-screen flex items-center justify-center bg-background">
                <Card className="max-w-md">
                    <CardContent className="p-8 text-center">
                        <MessageSquare className="h-12 w-12 text-muted-foreground mx-auto mb-4" />
                        <h2 className="text-xl font-semibold mb-2">Chat Not Found</h2>
                        <p className="text-muted-foreground">
                            This chat may have been removed or is no longer public.
                        </p>
                    </CardContent>
                </Card>
            </div>
        )
    }

    return (
        <div className="min-h-screen bg-background">
            {/* Header */}
            <header className="border-b bg-card">
                <div className="container mx-auto px-4 py-4">
                    <div className="flex items-center space-x-3">
                        <div className="h-10 w-10 rounded-xl bg-primary/10 flex items-center justify-center">
                            <Database className="h-5 w-5 text-primary" />
                        </div>
                        <div>
                            <h1 className="text-xl font-bold">{chat.connection_name}</h1>
                            <p className="text-sm text-muted-foreground">
                                {chat.database_name} • Shared Chat
                            </p>
                        </div>
                    </div>
                </div>
            </header>

            {/* Chat Content */}
            <main className="container mx-auto px-4 py-6">
                <Card className="max-w-4xl mx-auto">
                    <CardHeader className="border-b">
                        <CardTitle className="flex items-center gap-2">
                            <MessageSquare className="h-5 w-5" />
                            {chat.title || 'Chat Conversation'}
                        </CardTitle>
                    </CardHeader>
                    <CardContent className="p-4 space-y-4 max-h-[600px] overflow-auto">
                        {chat.messages?.map((msg: Message) => (
                            <div
                                key={msg.id}
                                className={cn(
                                    'max-w-[80%] rounded-lg p-4',
                                    msg.role === 'user'
                                        ? 'ml-auto bg-primary text-primary-foreground'
                                        : 'bg-muted'
                                )}
                            >
                                <p>{msg.content}</p>
                                {msg.sql && (
                                    <pre className="mt-3 p-3 bg-background rounded text-xs overflow-auto">
                                        <code>{msg.sql}</code>
                                    </pre>
                                )}
                                {msg.data && msg.data.length > 0 && (
                                    <div className="mt-3 overflow-auto">
                                        <table className="w-full text-xs border-collapse">
                                            <tbody>
                                                {msg.data.slice(0, 10).map((row: any, ri: number) => (
                                                    <tr key={ri} className="border-b border-muted">
                                                        {Object.values(row).map((cell: any, ci: number) => (
                                                            <td key={ci} className="p-2">{String(cell ?? '')}</td>
                                                        ))}
                                                    </tr>
                                                ))}
                                            </tbody>
                                        </table>
                                        {msg.data.length > 10 && (
                                            <p className="text-xs text-muted-foreground mt-2">
                                                Showing 10 of {msg.data.length} rows
                                            </p>
                                        )}
                                    </div>
                                )}
                                <p className="text-xs opacity-60 mt-2">
                                    {formatDateTime(msg.created_at)}
                                </p>
                            </div>
                        ))}
                        {(!chat.messages || chat.messages.length === 0) && (
                            <div className="text-center py-8 text-muted-foreground">
                                No messages in this conversation
                            </div>
                        )}
                    </CardContent>
                </Card>

                <p className="text-center text-sm text-muted-foreground mt-6">
                    This is a read-only view of a shared conversation.
                </p>
            </main>
        </div>
    )
}
