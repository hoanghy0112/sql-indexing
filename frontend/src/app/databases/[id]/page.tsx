'use client'

import { useEffect, useState } from 'react'
import { useRouter, useParams } from 'next/navigation'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { useToast } from '@/hooks/use-toast'
import { connectionsApi, intelligenceApi, chatApi, systemApi, usersApi } from '@/lib/api'
import { useAuthStore } from '@/lib/auth'
import { cn, formatDateTime, formatNumber } from '@/lib/utils'
import {
    ArrowLeft, Database, MessageSquare, Brain, Settings, Loader2,
    RefreshCw, Trash2, Share2, Send, CheckCircle2, AlertCircle,
    Table2, Columns, Hash, FileText, Sparkles, Save, UserPlus, X, Copy, Link
} from 'lucide-react'
import {
    Dialog,
    DialogContent,
    DialogDescription,
    DialogHeader,
    DialogTitle,
    DialogTrigger,
} from '@/components/ui/dialog'

export default function DatabasePage() {
    const router = useRouter()
    const params = useParams()
    const connectionId = parseInt(params.id as string)
    const { toast } = useToast()
    const queryClient = useQueryClient()
    const { isAuthenticated } = useAuthStore()

    const [activeTab, setActiveTab] = useState('general')
    const [chatInput, setChatInput] = useState('')
    const [explainMode, setExplainMode] = useState(true)
    const [chatMessages, setChatMessages] = useState<Array<{
        role: 'user' | 'assistant'
        content: string
        sql?: string
        data?: any[]
        columns?: string[]
    }>>([])

    // Settings form state
    const [editName, setEditName] = useState('')
    const [editDescription, setEditDescription] = useState('')
    const [editHost, setEditHost] = useState('')
    const [editPort, setEditPort] = useState(5432)
    const [editDatabase, setEditDatabase] = useState('')
    const [editUsername, setEditUsername] = useState('')
    const [editPassword, setEditPassword] = useState('')
    const [editSslMode, setEditSslMode] = useState('prefer')

    // Sharing state
    const [shareUserSearch, setShareUserSearch] = useState('')
    const [sharePermission, setSharePermission] = useState<'chat' | 'view' | 'owner'>('view')
    const [searchResults, setSearchResults] = useState<Array<{ id: number; username: string; email: string }>>([])
    const [selectedUser, setSelectedUser] = useState<{ id: number; username: string; email: string } | null>(null)
    const [isShareDialogOpen, setIsShareDialogOpen] = useState(false)

    // Chat share state
    const [currentSessionId, setCurrentSessionId] = useState<number | null>(null)
    const [chatShareInfo, setChatShareInfo] = useState<{ is_public: boolean; share_url: string | null } | null>(null)
    const [isChatShareDialogOpen, setIsChatShareDialogOpen] = useState(false)

    // Fetch connection details
    const { data: connection, isLoading } = useQuery({
        queryKey: ['connection', connectionId],
        queryFn: async () => {
            const response = await connectionsApi.get(connectionId)
            return response.data
        },
        enabled: isAuthenticated && !!connectionId,
        refetchInterval: 5000,
    })

    // Fetch insights
    const { data: insights } = useQuery({
        queryKey: ['insights', connectionId],
        queryFn: async () => {
            const response = await intelligenceApi.getInsights(connectionId)
            return response.data
        },
        enabled: isAuthenticated && !!connectionId && connection?.status === 'ready',
    })

    // Fetch stats
    const { data: stats } = useQuery({
        queryKey: ['stats', connectionId],
        queryFn: async () => {
            const response = await intelligenceApi.getStats(connectionId)
            return response.data
        },
        enabled: isAuthenticated && !!connectionId && connection?.status === 'ready',
    })

    // Reanalyze mutation
    const reanalyzeMutation = useMutation({
        mutationFn: () => connectionsApi.reanalyze(connectionId),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['connection', connectionId] })
            toast({ title: 'Re-analysis started' })
        },
        onError: (error: any) => {
            toast({
                title: 'Failed to start re-analysis',
                description: error.response?.data?.detail,
                variant: 'destructive',
            })
        },
    })

    // Delete mutation
    const deleteMutation = useMutation({
        mutationFn: () => connectionsApi.delete(connectionId),
        onSuccess: () => {
            toast({ title: 'Database deleted' })
            router.push('/')
        },
        onError: (error: any) => {
            toast({
                title: 'Failed to delete database',
                description: error.response?.data?.detail,
                variant: 'destructive',
            })
        },
    })

    // Chat mutation
    const chatMutation = useMutation({
        mutationFn: (question: string) =>
            chatApi.send(connectionId, { question, explain_mode: explainMode, session_id: currentSessionId || undefined }),
        onSuccess: (response) => {
            const data = response.data
            // Track session ID for sharing
            if (data.session_id && !currentSessionId) {
                setCurrentSessionId(data.session_id)
            }
            setChatMessages((prev) => [
                ...prev,
                {
                    role: 'assistant',
                    content: data.explanation || data.response || 'Query executed successfully',
                    sql: data.sql,
                    data: data.data,
                    columns: data.columns,
                },
            ])
        },
        onError: (error: any) => {
            setChatMessages((prev) => [
                ...prev,
                {
                    role: 'assistant',
                    content: `Error: ${error.response?.data?.detail || 'Failed to process your question'}`,
                },
            ])
        },
    })

    const handleSendMessage = () => {
        if (!chatInput.trim()) return

        setChatMessages((prev) => [...prev, { role: 'user', content: chatInput }])
        chatMutation.mutate(chatInput)
        setChatInput('')
    }

    // Update connection settings mutation
    const updateMutation = useMutation({
        mutationFn: (data: {
            name?: string
            description?: string
            host?: string
            port?: number
            database?: string
            username?: string
            password?: string
            ssl_mode?: string
        }) => connectionsApi.update(connectionId, data),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['connection', connectionId] })
            toast({ title: 'Connection updated', description: 'Settings saved successfully' })
            setEditPassword('') // Clear password after save
        },
        onError: (error: any) => {
            toast({
                title: 'Failed to update connection',
                description: error.response?.data?.detail || 'An error occurred',
                variant: 'destructive',
            })
        },
    })

    const handleSaveSettings = () => {
        const updateData: Record<string, any> = {}
        if (editName !== connection?.name) updateData.name = editName
        if (editDescription !== (connection?.description || '')) updateData.description = editDescription
        if (editHost !== connection?.host) updateData.host = editHost
        if (editPort !== connection?.port) updateData.port = editPort
        if (editDatabase !== connection?.database) updateData.database = editDatabase
        if (editUsername !== connection?.username) updateData.username = editUsername
        if (editPassword) updateData.password = editPassword
        if (editSslMode !== connection?.ssl_mode) updateData.ssl_mode = editSslMode

        if (Object.keys(updateData).length === 0) {
            toast({ title: 'No changes', description: 'No settings were changed' })
            return
        }

        updateMutation.mutate(updateData)
    }

    // Fetch shares
    const { data: sharesData, refetch: refetchShares } = useQuery({
        queryKey: ['shares', connectionId],
        queryFn: async () => {
            const response = await connectionsApi.listShares(connectionId)
            return response.data
        },
        enabled: isAuthenticated && !!connectionId,
    })

    // Add share mutation
    const addShareMutation = useMutation({
        mutationFn: (data: { user_id: number; permission: string }) =>
            connectionsApi.addShare(connectionId, data),
        onSuccess: () => {
            refetchShares()
            setSelectedUser(null)
            setShareUserSearch('')
            toast({ title: 'Share added', description: 'User can now access this database' })
        },
        onError: (error: any) => {
            toast({
                title: 'Failed to add share',
                description: error.response?.data?.detail || 'An error occurred',
                variant: 'destructive',
            })
        },
    })

    // Remove share mutation
    const removeShareMutation = useMutation({
        mutationFn: (userId: number) => connectionsApi.removeShare(connectionId, userId),
        onSuccess: () => {
            refetchShares()
            toast({ title: 'Share removed' })
        },
        onError: (error: any) => {
            toast({
                title: 'Failed to remove share',
                description: error.response?.data?.detail || 'An error occurred',
                variant: 'destructive',
            })
        },
    })

    // User search handler
    const handleUserSearch = async (query: string) => {
        setShareUserSearch(query)
        if (query.length < 2) {
            setSearchResults([])
            return
        }
        try {
            const response = await usersApi.search(query)
            setSearchResults(response.data || [])
        } catch (error) {
            setSearchResults([])
        }
    }

    // Handle add share
    const handleAddShare = () => {
        if (!selectedUser) return
        addShareMutation.mutate({ user_id: selectedUser.id, permission: sharePermission })
    }

    // Chat share toggle mutation
    const chatShareMutation = useMutation({
        mutationFn: (sessionId: number) => chatApi.toggleShare(connectionId, sessionId),
        onSuccess: (response) => {
            const data = response.data
            setChatShareInfo({ is_public: data.is_public, share_url: data.share_url })
            toast({
                title: data.is_public ? 'Chat is now public' : 'Chat is now private',
                description: data.is_public ? 'Anyone with the link can view this chat' : 'Chat link has been disabled',
            })
        },
        onError: (error: any) => {
            toast({
                title: 'Failed to update sharing',
                description: error.response?.data?.detail || 'An error occurred',
                variant: 'destructive',
            })
        },
    })

    // Initialize form state from connection data
    useEffect(() => {
        if (connection) {
            setEditName(connection.name || '')
            setEditDescription(connection.description || '')
            setEditHost(connection.host || '')
            setEditPort(connection.port || 5432)
            setEditDatabase(connection.database || '')
            setEditUsername(connection.username || '')
            setEditSslMode(connection.ssl_mode || 'prefer')
        }
    }, [connection])

    useEffect(() => {
        if (!isAuthenticated) {
            router.push('/login')
        }
    }, [isAuthenticated, router])

    if (isLoading || !connection) {
        return (
            <div className="min-h-screen flex items-center justify-center">
                <Loader2 className="h-8 w-8 animate-spin text-primary" />
            </div>
        )
    }

    const isProcessing = ['analyzing', 'indexing', 'updating'].includes(connection.status)
    const isReady = connection.status === 'ready'

    return (
        <div className="min-h-screen bg-background">
            {/* Header */}
            <header className="border-b bg-card">
                <div className="container mx-auto px-4 py-4">
                    <div className="flex items-center space-x-4">
                        <Button variant="ghost" size="sm" onClick={() => router.push('/')}>
                            <ArrowLeft className="h-4 w-4 mr-2" />
                            Back
                        </Button>
                        <div className="flex items-center space-x-3">
                            <div className="h-10 w-10 rounded-xl bg-primary/10 flex items-center justify-center">
                                <Database className="h-5 w-5 text-primary" />
                            </div>
                            <div>
                                <h1 className="text-xl font-bold">{connection.name}</h1>
                                <p className="text-sm text-muted-foreground">{connection.database}</p>
                            </div>
                        </div>
                        <div className={cn(
                            'ml-auto flex items-center space-x-2 px-3 py-1 rounded-full text-sm',
                            isReady ? 'bg-green-500/10 text-green-500' :
                                isProcessing ? 'bg-blue-500/10 text-blue-500' :
                                    'bg-red-500/10 text-red-500'
                        )}>
                            {isReady ? <CheckCircle2 className="h-4 w-4" /> :
                                isProcessing ? <RefreshCw className="h-4 w-4 animate-spin" /> :
                                    <AlertCircle className="h-4 w-4" />}
                            <span className="capitalize">{connection.status}</span>
                        </div>
                    </div>
                </div>
            </header>

            {/* Main Content */}
            <main className="container mx-auto px-4 py-6">
                {isProcessing && (
                    <Card className="mb-6 border-blue-500/50">
                        <CardContent className="py-4">
                            <div className="flex items-center space-x-4">
                                <RefreshCw className="h-5 w-5 text-blue-500 animate-spin" />
                                <div className="flex-1">
                                    <p className="font-medium">{connection.status_message || 'Processing...'}</p>
                                    <div className="h-2 mt-2 bg-muted rounded-full overflow-hidden">
                                        <div
                                            className="h-full bg-blue-500 transition-all"
                                            style={{ width: `${connection.analysis_progress}%` }}
                                        />
                                    </div>
                                </div>
                                <span className="text-sm text-muted-foreground">
                                    {Math.round(connection.analysis_progress)}%
                                </span>
                            </div>
                        </CardContent>
                    </Card>
                )}

                <Tabs value={activeTab} onValueChange={setActiveTab}>
                    <TabsList className="mb-6">
                        <TabsTrigger value="general" className="space-x-2">
                            <Database className="h-4 w-4" />
                            <span>General</span>
                        </TabsTrigger>
                        <TabsTrigger value="chat" className="space-x-2" disabled={!isReady}>
                            <MessageSquare className="h-4 w-4" />
                            <span>Ask DB</span>
                        </TabsTrigger>
                        <TabsTrigger value="intelligence" className="space-x-2" disabled={!isReady}>
                            <Brain className="h-4 w-4" />
                            <span>Intelligence</span>
                        </TabsTrigger>
                        <TabsTrigger value="settings" className="space-x-2">
                            <Settings className="h-4 w-4" />
                            <span>Settings</span>
                        </TabsTrigger>
                    </TabsList>

                    {/* General Tab */}
                    <TabsContent value="general">
                        <div className="grid gap-6 md:grid-cols-2">
                            <Card>
                                <CardHeader>
                                    <CardTitle>Connection Details</CardTitle>
                                </CardHeader>
                                <CardContent className="space-y-4">
                                    <div className="grid grid-cols-2 gap-4 text-sm">
                                        <div>
                                            <p className="text-muted-foreground">Host</p>
                                            <p className="font-medium">{connection.host}</p>
                                        </div>
                                        <div>
                                            <p className="text-muted-foreground">Port</p>
                                            <p className="font-medium">{connection.port}</p>
                                        </div>
                                        <div>
                                            <p className="text-muted-foreground">Database</p>
                                            <p className="font-medium">{connection.database}</p>
                                        </div>
                                        <div>
                                            <p className="text-muted-foreground">Username</p>
                                            <p className="font-medium">{connection.username}</p>
                                        </div>
                                    </div>
                                </CardContent>
                            </Card>

                            <Card>
                                <CardHeader>
                                    <CardTitle>Status</CardTitle>
                                </CardHeader>
                                <CardContent className="space-y-4">
                                    <div className="grid grid-cols-2 gap-4 text-sm">
                                        <div>
                                            <p className="text-muted-foreground">Status</p>
                                            <p className="font-medium capitalize">{connection.status}</p>
                                        </div>
                                        <div>
                                            <p className="text-muted-foreground">Last Analyzed</p>
                                            <p className="font-medium">
                                                {connection.last_analyzed_at
                                                    ? formatDateTime(connection.last_analyzed_at)
                                                    : 'Never'}
                                            </p>
                                        </div>
                                        <div>
                                            <p className="text-muted-foreground">Created</p>
                                            <p className="font-medium">{formatDateTime(connection.created_at)}</p>
                                        </div>
                                    </div>
                                </CardContent>
                            </Card>

                            {stats && (
                                <Card className="md:col-span-2">
                                    <CardHeader>
                                        <CardTitle>Analysis Summary</CardTitle>
                                    </CardHeader>
                                    <CardContent>
                                        <div className="grid grid-cols-2 md:grid-cols-4 gap-6">
                                            <div className="flex items-center space-x-3">
                                                <div className="h-10 w-10 rounded-lg bg-blue-500/10 flex items-center justify-center">
                                                    <Table2 className="h-5 w-5 text-blue-500" />
                                                </div>
                                                <div>
                                                    <p className="text-2xl font-bold">{stats.tables_analyzed}</p>
                                                    <p className="text-sm text-muted-foreground">Tables</p>
                                                </div>
                                            </div>
                                            <div className="flex items-center space-x-3">
                                                <div className="h-10 w-10 rounded-lg bg-green-500/10 flex items-center justify-center">
                                                    <Hash className="h-5 w-5 text-green-500" />
                                                </div>
                                                <div>
                                                    <p className="text-2xl font-bold">{formatNumber(stats.total_rows)}</p>
                                                    <p className="text-sm text-muted-foreground">Total Rows</p>
                                                </div>
                                            </div>
                                            <div className="flex items-center space-x-3">
                                                <div className="h-10 w-10 rounded-lg bg-purple-500/10 flex items-center justify-center">
                                                    <Sparkles className="h-5 w-5 text-purple-500" />
                                                </div>
                                                <div>
                                                    <p className="text-2xl font-bold">{stats.vectors_count}</p>
                                                    <p className="text-sm text-muted-foreground">Vectors</p>
                                                </div>
                                            </div>
                                        </div>
                                    </CardContent>
                                </Card>
                            )}
                        </div>
                    </TabsContent>

                    {/* Chat Tab */}
                    <TabsContent value="chat">
                        <Card className="h-[600px] flex flex-col">
                            <CardHeader className="border-b">
                                <div className="flex items-center justify-between">
                                    <CardTitle>Ask your Database</CardTitle>
                                    <div className="flex items-center space-x-4">
                                        <div className="flex items-center space-x-2">
                                            <Label htmlFor="explain-mode" className="text-sm">Explain Mode</Label>
                                            <input
                                                id="explain-mode"
                                                type="checkbox"
                                                checked={explainMode}
                                                onChange={(e) => setExplainMode(e.target.checked)}
                                                className="rounded"
                                            />
                                        </div>
                                        {chatMessages.length > 0 && currentSessionId && (
                                            <Dialog open={isChatShareDialogOpen} onOpenChange={setIsChatShareDialogOpen}>
                                                <DialogTrigger asChild>
                                                    <Button variant="outline" size="sm">
                                                        <Share2 className="h-4 w-4 mr-2" />
                                                        Share
                                                    </Button>
                                                </DialogTrigger>
                                                <DialogContent>
                                                    <DialogHeader>
                                                        <DialogTitle>Share this Chat</DialogTitle>
                                                        <DialogDescription>
                                                            Make this conversation public so anyone with the link can view it.
                                                        </DialogDescription>
                                                    </DialogHeader>
                                                    <div className="space-y-4 py-4">
                                                        <div className="flex items-center justify-between">
                                                            <div>
                                                                <p className="font-medium">Public Access</p>
                                                                <p className="text-sm text-muted-foreground">
                                                                    {chatShareInfo?.is_public
                                                                        ? 'Anyone with the link can view'
                                                                        : 'Only you can access this chat'}
                                                                </p>
                                                            </div>
                                                            <Button
                                                                variant={chatShareInfo?.is_public ? "destructive" : "default"}
                                                                onClick={() => chatShareMutation.mutate(currentSessionId)}
                                                                disabled={chatShareMutation.isPending}
                                                            >
                                                                {chatShareMutation.isPending ? (
                                                                    <Loader2 className="h-4 w-4 animate-spin" />
                                                                ) : chatShareInfo?.is_public ? (
                                                                    'Make Private'
                                                                ) : (
                                                                    'Make Public'
                                                                )}
                                                            </Button>
                                                        </div>
                                                        {chatShareInfo?.is_public && chatShareInfo?.share_url && (
                                                            <div className="space-y-2">
                                                                <Label>Share Link</Label>
                                                                <div className="flex gap-2">
                                                                    <Input
                                                                        value={`${window.location.origin}${chatShareInfo.share_url}`}
                                                                        readOnly
                                                                    />
                                                                    <Button
                                                                        variant="outline"
                                                                        onClick={() => {
                                                                            navigator.clipboard.writeText(`${window.location.origin}${chatShareInfo.share_url}`)
                                                                            toast({ title: 'Link copied!' })
                                                                        }}
                                                                    >
                                                                        <Copy className="h-4 w-4" />
                                                                    </Button>
                                                                </div>
                                                            </div>
                                                        )}
                                                    </div>
                                                </DialogContent>
                                            </Dialog>
                                        )}
                                    </div>
                                </div>
                            </CardHeader>
                            <CardContent className="flex-1 overflow-auto p-4 space-y-4">
                                {chatMessages.length === 0 ? (
                                    <div className="h-full flex flex-col items-center justify-center text-center">
                                        <MessageSquare className="h-12 w-12 text-muted-foreground mb-4" />
                                        <h3 className="text-lg font-medium mb-2">Start a conversation</h3>
                                        <p className="text-muted-foreground max-w-md">
                                            Ask questions about your data in natural language.
                                            I'll translate them to SQL and fetch the results.
                                        </p>
                                    </div>
                                ) : (
                                    chatMessages.map((msg, i) => (
                                        <div key={i} className={cn(
                                            'max-w-[80%] rounded-lg p-4',
                                            msg.role === 'user'
                                                ? 'ml-auto bg-primary text-primary-foreground'
                                                : 'bg-muted'
                                        )}>
                                            <p>{msg.content}</p>
                                            {msg.sql && (
                                                <pre className="mt-3 p-3 bg-background rounded text-xs overflow-auto">
                                                    <code>{msg.sql}</code>
                                                </pre>
                                            )}
                                            {msg.data && msg.data.length > 0 && msg.columns && (
                                                <div className="mt-3 overflow-auto">
                                                    <table className="w-full text-xs">
                                                        <thead>
                                                            <tr className="border-b">
                                                                {msg.columns.map((col) => (
                                                                    <th key={col} className="text-left p-2 font-medium">{col}</th>
                                                                ))}
                                                            </tr>
                                                        </thead>
                                                        <tbody>
                                                            {msg.data.slice(0, 10).map((row, ri) => (
                                                                <tr key={ri} className="border-b border-muted">
                                                                    {row.map((cell: any, ci: number) => (
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
                                        </div>
                                    ))
                                )}
                                {chatMutation.isPending && (
                                    <div className="flex items-center space-x-2 text-muted-foreground">
                                        <Loader2 className="h-4 w-4 animate-spin" />
                                        <span>Thinking...</span>
                                    </div>
                                )}
                            </CardContent>
                            <div className="border-t p-4">
                                <div className="flex space-x-2">
                                    <Input
                                        placeholder="Ask a question about your data..."
                                        value={chatInput}
                                        onChange={(e) => setChatInput(e.target.value)}
                                        onKeyDown={(e) => e.key === 'Enter' && !e.shiftKey && handleSendMessage()}
                                        disabled={chatMutation.isPending}
                                    />
                                    <Button onClick={handleSendMessage} disabled={chatMutation.isPending}>
                                        <Send className="h-4 w-4" />
                                    </Button>
                                </div>
                            </div>
                        </Card>
                    </TabsContent>

                    {/* Intelligence Tab */}
                    <TabsContent value="intelligence">
                        <div className="space-y-6">
                            <div className="flex items-center justify-between">
                                <div>
                                    <h3 className="text-lg font-medium">Database Insights</h3>
                                    <p className="text-muted-foreground">
                                        AI-generated insights about your database schema
                                    </p>
                                </div>
                                <Button
                                    variant="outline"
                                    onClick={() => reanalyzeMutation.mutate()}
                                    disabled={reanalyzeMutation.isPending || isProcessing}
                                >
                                    {reanalyzeMutation.isPending ? (
                                        <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                                    ) : (
                                        <RefreshCw className="h-4 w-4 mr-2" />
                                    )}
                                    Re-analyze
                                </Button>
                            </div>

                            <div className="grid gap-4 md:grid-cols-2">
                                {insights?.map((insight: any) => (
                                    <Card key={insight.id}>
                                        <CardHeader className="pb-3">
                                            <div className="flex items-center space-x-2">
                                                <Table2 className="h-4 w-4 text-primary" />
                                                <CardTitle className="text-base">
                                                    {insight.schema_name}.{insight.table_name}
                                                </CardTitle>
                                            </div>
                                            <CardDescription>
                                                {formatNumber(insight.row_count)} rows • {insight.columns.length} columns
                                            </CardDescription>
                                        </CardHeader>
                                        <CardContent>
                                            <div className="space-y-2">
                                                {insight.columns.slice(0, 5).map((col: any) => (
                                                    <div key={col.name} className="flex items-center justify-between text-sm">
                                                        <div className="flex items-center space-x-2">
                                                            <Columns className="h-3 w-3 text-muted-foreground" />
                                                            <span>{col.name}</span>
                                                            <span className="text-xs text-muted-foreground">({col.data_type})</span>
                                                        </div>
                                                        <span className={cn(
                                                            'text-xs px-2 py-0.5 rounded',
                                                            col.indexing_strategy === 'categorical' ? 'bg-green-500/10 text-green-500' :
                                                                col.indexing_strategy === 'vector' ? 'bg-purple-500/10 text-purple-500' :
                                                                    'bg-muted text-muted-foreground'
                                                        )}>
                                                            {col.indexing_strategy}
                                                        </span>
                                                    </div>
                                                ))}
                                                {insight.columns.length > 5 && (
                                                    <p className="text-xs text-muted-foreground">
                                                        +{insight.columns.length - 5} more columns
                                                    </p>
                                                )}
                                            </div>
                                        </CardContent>
                                    </Card>
                                ))}
                            </div>
                        </div>
                    </TabsContent>

                    {/* Settings Tab */}
                    <TabsContent value="settings">
                        <div className="max-w-2xl space-y-6">
                            <Card>
                                <CardHeader>
                                    <CardTitle>Connection Settings</CardTitle>
                                    <CardDescription>
                                        Update your database connection details
                                    </CardDescription>
                                </CardHeader>
                                <CardContent className="space-y-4">
                                    <div className="space-y-2">
                                        <Label htmlFor="name">Connection Name</Label>
                                        <Input
                                            id="name"
                                            value={editName}
                                            onChange={(e) => setEditName(e.target.value)}
                                            placeholder="My Database"
                                        />
                                    </div>
                                    <div className="space-y-2">
                                        <Label htmlFor="description">Description</Label>
                                        <Input
                                            id="description"
                                            value={editDescription}
                                            onChange={(e) => setEditDescription(e.target.value)}
                                            placeholder="Optional description"
                                        />
                                    </div>
                                    <div className="grid grid-cols-2 gap-4">
                                        <div className="space-y-2">
                                            <Label htmlFor="host">Host</Label>
                                            <Input
                                                id="host"
                                                value={editHost}
                                                onChange={(e) => setEditHost(e.target.value)}
                                                placeholder="localhost"
                                            />
                                        </div>
                                        <div className="space-y-2">
                                            <Label htmlFor="port">Port</Label>
                                            <Input
                                                id="port"
                                                type="number"
                                                value={editPort}
                                                onChange={(e) => setEditPort(parseInt(e.target.value) || 5432)}
                                                placeholder="5432"
                                            />
                                        </div>
                                    </div>
                                    <div className="space-y-2">
                                        <Label htmlFor="database">Database</Label>
                                        <Input
                                            id="database"
                                            value={editDatabase}
                                            onChange={(e) => setEditDatabase(e.target.value)}
                                            placeholder="my_database"
                                        />
                                    </div>
                                    <div className="grid grid-cols-2 gap-4">
                                        <div className="space-y-2">
                                            <Label htmlFor="username">Username</Label>
                                            <Input
                                                id="username"
                                                value={editUsername}
                                                onChange={(e) => setEditUsername(e.target.value)}
                                                placeholder="postgres"
                                            />
                                        </div>
                                        <div className="space-y-2">
                                            <Label htmlFor="password">Password</Label>
                                            <Input
                                                id="password"
                                                type="password"
                                                value={editPassword}
                                                onChange={(e) => setEditPassword(e.target.value)}
                                                placeholder="Leave blank to keep current"
                                            />
                                        </div>
                                    </div>
                                    <div className="space-y-2">
                                        <Label htmlFor="ssl_mode">SSL Mode</Label>
                                        <select
                                            id="ssl_mode"
                                            value={editSslMode}
                                            onChange={(e) => setEditSslMode(e.target.value)}
                                            className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
                                        >
                                            <option value="disable">Disable</option>
                                            <option value="prefer">Prefer</option>
                                            <option value="require">Require</option>
                                        </select>
                                    </div>
                                    <div className="pt-4">
                                        <Button
                                            onClick={handleSaveSettings}
                                            disabled={updateMutation.isPending}
                                            className="w-full"
                                        >
                                            {updateMutation.isPending ? (
                                                <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                                            ) : (
                                                <Save className="h-4 w-4 mr-2" />
                                            )}
                                            Save Changes
                                        </Button>
                                    </div>
                                </CardContent>
                            </Card>

                            {/* Share Database Card */}
                            <Card>
                                <CardHeader>
                                    <CardTitle className="flex items-center gap-2">
                                        <Share2 className="h-5 w-5" />
                                        Share Database
                                    </CardTitle>
                                    <CardDescription>
                                        Share this database with other users
                                    </CardDescription>
                                </CardHeader>
                                <CardContent className="space-y-4">
                                    {/* Add new share */}
                                    <div className="space-y-3">
                                        <div className="flex gap-2">
                                            <div className="flex-1 relative">
                                                <Input
                                                    placeholder="Search users by email or username..."
                                                    value={shareUserSearch}
                                                    onChange={(e) => handleUserSearch(e.target.value)}
                                                />
                                                {searchResults.length > 0 && (
                                                    <div className="absolute z-10 w-full mt-1 bg-popover border rounded-md shadow-lg max-h-40 overflow-auto">
                                                        {searchResults.map((user) => (
                                                            <div
                                                                key={user.id}
                                                                className="px-3 py-2 hover:bg-muted cursor-pointer text-sm"
                                                                onClick={() => {
                                                                    setSelectedUser(user)
                                                                    setShareUserSearch(user.email)
                                                                    setSearchResults([])
                                                                }}
                                                            >
                                                                <span className="font-medium">{user.username}</span>
                                                                <span className="text-muted-foreground ml-2">{user.email}</span>
                                                            </div>
                                                        ))}
                                                    </div>
                                                )}
                                            </div>
                                            <select
                                                value={sharePermission}
                                                onChange={(e) => setSharePermission(e.target.value as 'chat' | 'view' | 'owner')}
                                                className="h-10 rounded-md border border-input bg-background px-3 text-sm"
                                            >
                                                <option value="chat">Chat Only</option>
                                                <option value="view">View</option>
                                                <option value="owner">Owner</option>
                                            </select>
                                            <Button
                                                onClick={handleAddShare}
                                                disabled={!selectedUser || addShareMutation.isPending}
                                            >
                                                {addShareMutation.isPending ? (
                                                    <Loader2 className="h-4 w-4 animate-spin" />
                                                ) : (
                                                    <UserPlus className="h-4 w-4" />
                                                )}
                                            </Button>
                                        </div>
                                        <p className="text-xs text-muted-foreground">
                                            <strong>Chat:</strong> Ask DB only | <strong>View:</strong> Chat + Intelligence | <strong>Owner:</strong> Full access
                                        </p>
                                    </div>

                                    {/* Current shares */}
                                    <div className="space-y-2">
                                        <h4 className="text-sm font-medium">Current Access</h4>
                                        {sharesData?.owner && (
                                            <div className="flex items-center justify-between py-2 px-3 rounded-md bg-muted/50">
                                                <div className="flex items-center gap-2">
                                                    <span className="text-sm font-medium">{sharesData.owner.username}</span>
                                                    <span className="text-xs text-muted-foreground">{sharesData.owner.email}</span>
                                                </div>
                                                <span className="text-xs px-2 py-0.5 rounded bg-primary/10 text-primary">Owner</span>
                                            </div>
                                        )}
                                        {sharesData?.shares?.map((share: any) => (
                                            <div key={share.id} className="flex items-center justify-between py-2 px-3 rounded-md bg-muted/50">
                                                <div className="flex items-center gap-2">
                                                    <span className="text-sm font-medium">{share.username}</span>
                                                    <span className="text-xs text-muted-foreground">{share.email}</span>
                                                </div>
                                                <div className="flex items-center gap-2">
                                                    <span className={cn(
                                                        "text-xs px-2 py-0.5 rounded",
                                                        share.permission === 'owner' ? 'bg-purple-500/10 text-purple-500' :
                                                            share.permission === 'view' ? 'bg-blue-500/10 text-blue-500' :
                                                                'bg-green-500/10 text-green-500'
                                                    )}>
                                                        {share.permission}
                                                    </span>
                                                    <Button
                                                        variant="ghost"
                                                        size="sm"
                                                        onClick={() => removeShareMutation.mutate(share.user_id)}
                                                        disabled={removeShareMutation.isPending}
                                                    >
                                                        <X className="h-4 w-4" />
                                                    </Button>
                                                </div>
                                            </div>
                                        ))}
                                        {(!sharesData?.shares || sharesData.shares.length === 0) && (
                                            <p className="text-sm text-muted-foreground py-2">No users have been added yet</p>
                                        )}
                                    </div>
                                </CardContent>
                            </Card>

                            <Card className="border-red-500/50">
                                <CardHeader>
                                    <CardTitle className="text-red-500">Danger Zone</CardTitle>
                                    <CardDescription>
                                    </CardDescription>
                                </CardHeader>
                                <CardContent>
                                    <Button
                                        variant="outline"
                                        onClick={() => reanalyzeMutation.mutate()}
                                        disabled={reanalyzeMutation.isPending || isProcessing}
                                        className="w-full justify-start"
                                    >
                                        {reanalyzeMutation.isPending ? (
                                            <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                                        ) : (
                                            <RefreshCw className="h-4 w-4 mr-2" />
                                        )}
                                        Re-index Database
                                    </Button>
                                    <p className="text-xs text-muted-foreground mt-2">
                                        This will re-analyze the database schema and regenerate all embeddings.
                                    </p>
                                </CardContent>
                            </Card>

                            <Card className="border-red-500/50">
                                <CardHeader>
                                    <CardTitle className="text-red-500">Danger Zone</CardTitle>
                                    <CardDescription>
                                        Irreversible actions
                                    </CardDescription>
                                </CardHeader>
                                <CardContent>
                                    <Button
                                        variant="destructive"
                                        onClick={() => {
                                            if (confirm('Are you sure you want to delete this database connection?')) {
                                                deleteMutation.mutate()
                                            }
                                        }}
                                        disabled={deleteMutation.isPending}
                                    >
                                        {deleteMutation.isPending ? (
                                            <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                                        ) : (
                                            <Trash2 className="h-4 w-4 mr-2" />
                                        )}
                                        Delete Connection
                                    </Button>
                                </CardContent>
                            </Card>
                        </div>
                    </TabsContent>
                </Tabs>
            </main>
        </div>
    )
}
