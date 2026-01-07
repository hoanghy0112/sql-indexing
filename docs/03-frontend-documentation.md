# Frontend Documentation

This document provides detailed documentation for the frontend application, including its structure, components, and state management.

---

## Table of Contents

1. [Technology Stack](#technology-stack)
2. [Directory Structure](#directory-structure)
3. [Pages and Routing](#pages-and-routing)
4. [State Management](#state-management)
5. [API Client](#api-client)
6. [Components](#components)
7. [Theming](#theming)
8. [Build and Development](#build-and-development)

---

## Technology Stack

| Technology | Version | Purpose |
|------------|---------|---------|
| Next.js | 14.x | React framework with App Router |
| React | 18.x | UI library |
| TypeScript | 5.x | Type safety |
| React Query | 5.x | Server state management |
| Zustand | 4.x | Client state management |
| Tailwind CSS | 3.x | Utility-first CSS |
| Radix UI | Various | Accessible UI primitives |
| Lucide React | 0.311 | Icon library |
| Axios | 1.6 | HTTP client |
| next-themes | 0.4 | Theme switching |

---

## Directory Structure

```
frontend/src/
├── app/                    # Next.js App Router
│   ├── layout.tsx         # Root layout
│   ├── page.tsx           # Home page (connections list)
│   ├── providers.tsx      # React Query provider
│   ├── globals.css        # Global styles
│   ├── login/             # Login page
│   ├── register/          # Registration page
│   ├── databases/         # Database detail pages
│   │   └── [id]/
│   │       └── page.tsx   # Database detail view
│   └── chat/              # Public chat sharing
│       └── [token]/
│           └── page.tsx   # Public shared chat
│
├── components/
│   ├── ui/                # Shadcn UI components
│   │   ├── button.tsx
│   │   ├── card.tsx
│   │   ├── dialog.tsx
│   │   ├── input.tsx
│   │   ├── label.tsx
│   │   ├── progress.tsx
│   │   ├── tabs.tsx
│   │   └── toast.tsx
│   ├── theme-provider.tsx # Theme context provider
│   └── theme-toggle.tsx   # Light/dark mode toggle
│
├── lib/
│   ├── api.ts             # API client and endpoints
│   ├── auth.ts            # Authentication store
│   └── utils.ts           # Utility functions
│
└── hooks/
    └── use-toast.ts       # Toast notification hook
```

---

## Pages and Routing

### Home Page (`/`)
**File**: `app/page.tsx`

Main dashboard showing user's database connections.

**Features**:
- List of owned and shared connections
- Add new connection dialog
- Connection status indicators
- Logout functionality

**State**:
- `connections`: List of database connections (React Query)
- `user`: Current authenticated user (React Query)
- `formData`: Form state for new connection

### Login Page (`/login`)
**File**: `app/login/page.tsx`

User authentication page.

**Features**:
- Username/password login
- Link to registration
- Error handling

### Register Page (`/register`)
**File**: `app/register/page.tsx`

New user registration.

**Features**:
- Username, email, password fields
- Email validation
- Redirect to login on success

### Database Detail Page (`/databases/[id]`)
**File**: `app/databases/[id]/page.tsx`

Detailed view of a specific database connection.

**Features**:
- **General Tab**: Connection overview, status, sharing
- **Chat Tab**: Natural language query interface
- **Intelligence Tab**: Table insights and metadata
- **Settings Tab**: Connection configuration

**Tab Visibility by Permission**:
| Permission | General | Chat | Intelligence | Settings |
|------------|---------|------|--------------|----------|
| Owner | ✓ | ✓ | ✓ | ✓ |
| View | ✓ | ✓ | ✓ | ✗ |
| Chat | ✓ | ✓ | ✗ | ✗ |

### Public Chat Page (`/chat/[token]`)
**File**: `app/chat/[token]/page.tsx`

View publicly shared chat sessions (no authentication required).

---

## State Management

### Client State (Zustand)

**File**: `lib/auth.ts`

```typescript
interface AuthState {
  token: string | null
  user: User | null
  isAuthenticated: boolean
  setToken: (token: string) => void
  setUser: (user: User) => void
  logout: () => void
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      token: null,
      user: null,
      isAuthenticated: false,
      setToken: (token) => {
        localStorage.setItem('token', token)
        set({ token, isAuthenticated: true })
      },
      setUser: (user) => set({ user }),
      logout: () => {
        localStorage.removeItem('token')
        set({ token: null, user: null, isAuthenticated: false })
      },
    }),
    {
      name: 'auth-storage',
      partialize: (state) => ({ token: state.token }),
    }
  )
)
```

### Server State (React Query)

**File**: `app/providers.tsx`

```typescript
const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 60 * 1000, // 1 minute
      retry: 1,
    },
  },
})

export function Providers({ children }: { children: React.ReactNode }) {
  return (
    <QueryClientProvider client={queryClient}>
      <ThemeProvider>
        {children}
      </ThemeProvider>
    </QueryClientProvider>
  )
}
```

**Common Query Patterns**:

```typescript
// Fetch connections list
const { data: connections, isLoading } = useQuery({
  queryKey: ['connections'],
  queryFn: async () => {
    const response = await connectionsApi.list()
    return response.data
  },
})

// Mutation with cache invalidation
const mutation = useMutation({
  mutationFn: (data) => connectionsApi.create(data),
  onSuccess: () => {
    queryClient.invalidateQueries({ queryKey: ['connections'] })
  },
})
```

---

## API Client

**File**: `lib/api.ts`

### Base Configuration

```typescript
const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

export const api = axios.create({
  baseURL: API_URL,
  headers: {
    'Content-Type': 'application/json',
  },
})
```

### Request Interceptor (Auth Token)

```typescript
api.interceptors.request.use((config) => {
  if (typeof window !== 'undefined') {
    const token = localStorage.getItem('token')
    if (token) {
      config.headers.Authorization = `Bearer ${token}`
    }
  }
  return config
})
```

### Response Interceptor (401 Handling)

```typescript
api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      if (typeof window !== 'undefined') {
        localStorage.removeItem('token')
        window.location.href = '/login'
      }
    }
    return Promise.reject(error)
  }
)
```

### API Namespaces

#### authApi
```typescript
authApi.register({ username, email, password })
authApi.login({ username, password })
authApi.me()
authApi.refresh()
```

#### connectionsApi
```typescript
connectionsApi.list()
connectionsApi.get(id)
connectionsApi.create(data)
connectionsApi.createFromUrl(data)
connectionsApi.update(id, data)
connectionsApi.delete(id)
connectionsApi.test(id)
connectionsApi.reanalyze(id)
connectionsApi.listShares(id)
connectionsApi.addShare(id, data)
connectionsApi.removeShare(connectionId, userId)
```

#### intelligenceApi
```typescript
intelligenceApi.getInsights(connectionId)
intelligenceApi.getStats(connectionId)
intelligenceApi.updateInsight(connectionId, insightId, data)
```

#### chatApi
```typescript
chatApi.send(connectionId, { question, explain_mode, session_id })
chatApi.listSessions(connectionId)
chatApi.getSession(connectionId, sessionId)
chatApi.deleteSession(connectionId, sessionId)
chatApi.toggleShare(connectionId, sessionId)
chatApi.getPublicChat(shareToken)
```

#### systemApi
```typescript
systemApi.health()
systemApi.getConnectionStatus(connectionId)
systemApi.getSqlHistory(connectionId, limit, offset)
systemApi.getStats()
```

#### usersApi
```typescript
usersApi.search(query)
usersApi.updateProfile(data)
usersApi.changePassword(data)
```

### Error Handling

```typescript
export function getErrorMessage(error: any): string {
  if (!error.response) {
    return error.message || 'A network error occurred.'
  }
  const data = error.response.data
  
  // Handle FastAPI HTTPException
  if (typeof data.detail === 'string') {
    return data.detail
  }
  
  // Handle validation errors
  if (Array.isArray(data.detail)) {
    return data.detail
      .map((err) => `${err.loc?.join('.')}: ${err.msg}`)
      .join(', ')
  }
  
  return data.message || data.error || 'An unexpected error occurred.'
}
```

---

## Components

### UI Components (Shadcn)

Based on Radix UI primitives with Tailwind CSS styling.

| Component | File | Description |
|-----------|------|-------------|
| Button | `ui/button.tsx` | Variants: default, secondary, outline, ghost |
| Card | `ui/card.tsx` | Container with header, content, footer |
| Dialog | `ui/dialog.tsx` | Modal dialogs |
| Input | `ui/input.tsx` | Text inputs |
| Label | `ui/label.tsx` | Form labels |
| Progress | `ui/progress.tsx` | Progress bars |
| Tabs | `ui/tabs.tsx` | Tabbed interface |
| Toast | `ui/toast.tsx` | Notifications |
| ScrollArea | `ui/scroll-area.tsx` | Scrollable containers |
| Separator | `ui/separator.tsx` | Visual dividers |
| Avatar | `ui/avatar.tsx` | User avatars |
| Switch | `ui/switch.tsx` | Toggle switches |
| DropdownMenu | `ui/dropdown-menu.tsx` | Dropdown menus |

### Theme Components

#### ThemeProvider
**File**: `components/theme-provider.tsx`

Wraps the application with theme context using `next-themes`.

```typescript
export function ThemeProvider({
  children,
  ...props
}: ThemeProviderProps) {
  return (
    <NextThemesProvider {...props}>
      {children}
    </NextThemesProvider>
  )
}
```

#### ThemeToggle
**File**: `components/theme-toggle.tsx`

Button to toggle between light, dark, and system themes.

---

## Theming

### Color Scheme

The application uses a light/dark theme with emerald/green as the primary color.

**CSS Variables** (`globals.css`):

```css
:root {
  --background: 0 0% 100%;
  --foreground: 240 10% 3.9%;
  --primary: 142.1 76.2% 36.3%;
  --primary-foreground: 355.7 100% 97.3%;
  /* ... */
}

.dark {
  --background: 240 10% 3.9%;
  --foreground: 0 0% 98%;
  --primary: 142.1 70.6% 45.3%;
  /* ... */
}
```

### Tailwind Configuration

**File**: `tailwind.config.js`

```javascript
module.exports = {
  darkMode: ['class'],
  content: ['./src/**/*.{js,ts,jsx,tsx,mdx}'],
  theme: {
    extend: {
      colors: {
        border: 'hsl(var(--border))',
        background: 'hsl(var(--background))',
        foreground: 'hsl(var(--foreground))',
        primary: {
          DEFAULT: 'hsl(var(--primary))',
          foreground: 'hsl(var(--primary-foreground))',
        },
        // ...
      },
    },
  },
  plugins: [require('tailwindcss-animate')],
}
```

---

## Build and Development

### Development

```bash
# Install dependencies
npm install
# or
pnpm install

# Start development server
npm run dev
# or
pnpm dev

# Open http://localhost:3000
```

### Production Build

```bash
# Build for production
npm run build

# Start production server
npm start
```

### Linting & Formatting

```bash
# Run ESLint
npm run lint

# Format with Prettier
npm run format
```

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `NEXT_PUBLIC_API_URL` | Backend API URL | `http://localhost:8000` |

---

## Best Practices

### Error Handling
- Use `getErrorMessage()` helper for consistent error display
- Show toast notifications for API errors
- Handle 401 responses with automatic redirect to login

### Data Fetching
- Use React Query for all server state
- Set appropriate `staleTime` for caching
- Invalidate queries after mutations

### Type Safety
- Define interfaces for all API responses
- Use TypeScript strict mode
- Avoid `any` types

### Component Patterns
- Use Shadcn components as base
- Compose complex UIs from primitives
- Keep components focused and reusable
